import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from typing import Dict, Any

from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
# from converter.utils.extract_complete_block import extract_complete_block_with_normalized_indentation
from converter.utils.getLogger import setup_logging
from converter.utils.extract_block_by_scope import extract_block_by_scope
from converter.utils.yaml_to_string import yaml_to_string

# 设置日志
logger = setup_logging()

# 定义一个全局变量，来表示转换后的github的PATH环境变量
GITHUB_PATH_VALUE = ""


def parse_environment_block(content: str, scope="global") -> Dict[str, str]:
    """
    解析 Jenkinsfile.groovy. 中的 environment 块，提取环境变量信息。
    """
    global GITHUB_PATH_VALUE  # 声明要修改全局变量
    environment = {}
    # 使用通用函数提取environment块内容
    environment_content = extract_block_by_scope(content, 'environment', scope)

    if not environment_content:
        return environment

    logger.info(f"Environment_content [{scope}]: {environment_content}")

    # 匹配环境变量定义，如 VAR1 = "value1"
    env_var_pattern = re.compile(
        r'(\w+)\s*=\s*[\'"]([^\'"]*)[\'"]'
    )
    for m in env_var_pattern.finditer(environment_content):
        var_name, var_value = m.groups()
        environment[var_name] = var_value
        # 当环境变量类型为PATH时，变量在step中进行处理，而不是在GHA的env字段中进行定义，此时返回一个空变量
        if var_name == 'PATH':
            GITHUB_PATH_VALUE = convert_jenkins_path_to_github(var_value)
            return {}
    logger.info(f"Environment Parsed:: {environment}")
    return environment


def generate_yaml(environment: Dict[str, str]) -> Dict[str, Any]:
    """
    生成 GitHub Actions 的 environment 字典。
    """
    yaml_content = {
        PlainScalarString('env'): environment
    }
    return yaml_content


def environment_to_yaml(jenkinsfile_content: str, scope="global") -> Dict[str, Any]:
    """
    Convert Jenkins environment variables to YAML format for GitHub Actions.
    Args:
        jenkinsfile_content (str): Content of the Jenkinsfile to parse
        scope (str, optional): Scope of environment variables. Defaults to "global".
            Can be "global" or other scopes depending on pipeline structure.
    Returns:
        Dict[str, Any]: Dictionary containing environment variables in YAML format,
            or empty dict if no environment variables found.
    """
    # Parse environment block from Jenkinsfile content
    environment = parse_environment_block(jenkinsfile_content, scope)
    # If no environment variables found, log info and return empty dict
    if not environment:
        logger.info("No environment variables found in Jenkinsfile.groovy or PATH environment variable should be used in other ways.")
        return environment
    # Handle global scope environment variables
    if scope == "global":
        # 生成 YAML 字典
        github_actions_yaml_dict = generate_yaml(environment)
        jenkins_comparison = JenkinsComparisonSingle()
        jenkins_comparison.add_comparison(yaml_to_string(github_actions_yaml_dict), 'environment', scope)
        return github_actions_yaml_dict
    else:
        return environment


def convert_jenkins_path_to_github(jenkins_path_value: str) -> str:
    """
        将 Jenkins PATH 环境变量值转换为 GitHub Actions 的等价路径字符串。

        该方法能够处理以下通用情况：
        1. 忽略 "${env.PATH}:" 前缀，只提取需要添加的新路径。
        2. 将用户家目录路径（例如 "/home/jenkins"）转换为通用的 "$HOME"。
        3. 支持任意工具和路径，不仅仅是 asdf。

        Args:
            jenkins_path_value (str): Jenkinsfile 中 PATH 环境变量的值。
                                     例如: "${env.PATH}:/home/jenkins/.asdf/shims:/home/jenkins/.asdf/bin"

        Returns:
            str: 适用于 GitHub Actions 的、以冒号分隔的路径字符串。
                 例如: "$HOME/.asdf/shims:$HOME/.asdf/bin"
        """
    # 步骤 1: 提取新路径
    # 找到第一个冒号后的所有内容，忽略 "${env.PATH}:" 前缀。
    path_to_add = jenkins_path_value
    prefix = "${env.PATH}:"
    if jenkins_path_value.startswith(prefix):
        path_to_add = jenkins_path_value[len(prefix):]

    # 将路径字符串分割成列表
    new_paths = path_to_add.split(':')

    converted_paths = []

    # 步骤 2: 标准化路径
    # 遍历每个路径并进行转换
    for path in new_paths:
        path = path.strip()
        if not path:
            continue

        # 检查是否是用户家目录路径，并进行通用替换
        # 匹配 /home/jenkins 或者 /var/jenkins_home 等常见模式
        if path.startswith('/home/jenkins') or path.startswith('/var/jenkins_home'):
            # 使用 split() 方法来通用地替换家目录部分，保留后续路径
            parts = path.split('/home/jenkins')
            if len(parts) > 1:
                converted_path = f"$HOME{parts[1]}"
            else:
                parts = path.split('/var/jenkins_home')
                if len(parts) > 1:
                    converted_path = f"$HOME{parts[1]}"
                else:
                    converted_path = path
        else:
            # 如果不是用户家目录，则保持原样
            converted_path = path

        converted_paths.append(converted_path)

    # 步骤 3: 重新连接路径
    return ':'.join(converted_paths)


def main():
    # 读取 Jenkinsfile.groovy. 内容
    try:
        with open('../Jenkinsfile.groovy', 'r') as f:
            jenkinsfile_content = f.read()
    except FileNotFoundError:
        logger.error("Jenkinsfile.groovy.groovy not found in the current directory.")
        return

    # 解析环境变量
    environment = parse_environment_block(jenkinsfile_content)

    if not environment:
        print("No environment variables found in Jenkinsfile.groovy.")
        return

    # 生成 YAML 字典
    github_actions_yaml_dict = generate_yaml(environment)

    # 使用 ruamel.yaml 生成 YAML 字符串
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)

    # 写入文件
    output_file = 'github_actions_environment.yaml'
    with open(output_file, 'w') as f:
        yaml.dump(github_actions_yaml_dict, f)

    # 输出结果
    print("Generated GitHub Actions Environment YAML:")
    with open(output_file, 'r') as f:
        print(f.read())
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()
