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


def parse_environment_block(content: str, scope="global") -> Dict[str, str]:
    """
    解析 Jenkinsfile.groovy. 中的 environment 块，提取环境变量信息。
    """
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
    environment = parse_environment_block(jenkinsfile_content, scope)
    if not environment:
        logger.info("No environment variables found in Jenkinsfile.groovy.")
        return environment
    if scope == "global":
        # 生成 YAML 字典
        github_actions_yaml_dict = generate_yaml(environment)
        jenkins_comparison = JenkinsComparisonSingle()
        jenkins_comparison.add_comparison(yaml_to_string(github_actions_yaml_dict), 'environment', scope)
        return github_actions_yaml_dict
    else:
        return environment


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
