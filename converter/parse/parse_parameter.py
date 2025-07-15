import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PlainScalarString
from typing import Dict, Any

from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
from converter.utils.extract_block_by_scope import extract_block_by_scope
from converter.utils.extract_complete_block import extract_complete_block_with_normalized_indentation
from converter.utils.getLogger import setup_logging
from converter.utils.yaml_to_string import yaml_to_string

# 设置日志
logger = setup_logging()


def parse_parameters_block(jenkinsfile_content: str) -> Dict[str, Dict[str, Any]]:
    """
    解析 Jenkinsfile.groovy.groovy 中的 parameters 块，提取参数信息。
    """
    parameters = {}
    # 匹配 parameters 块
    parameters_block_pattern = re.compile(r'parameters\s*\{(.*?)}', re.DOTALL)
    match = parameters_block_pattern.search(jenkinsfile_content)
    if not match:
        logger.info("No parameters block found in Jenkinsfile.groovy.")
        return parameters  # 没有参数定义

    parameters_content = match.group(1)

    # 匹配 string 参数
    string_param_pattern = re.compile(
        r'string\s*\(\s*name\s*:\s*[\'"](\w+)[\'"]\s*,\s*defaultValue\s*:\s*[\'"]([^\'"]*)[\'"]\s*,\s*description\s*:\s*[\'"]([^\'"]*)[\'"]\s*\)'
    )
    for m in string_param_pattern.finditer(parameters_content):
        name, default, description = m.groups()
        parameters[name] = {
            'description': description,
            'default': default,
            'required': False,  # Jenkins 默认为可选，GitHub Actions 默认为 false
            'type': 'string'
        }

    # 匹配 booleanParam 参数
    boolean_param_pattern = re.compile(
        r'booleanParam\s*\(\s*name\s*:\s*[\'"](\w+)[\'"]\s*,\s*defaultValue\s*:\s*(true|false)\s*,\s*description\s*:\s*[\'"]([^\'"]*)[\'"]\s*\)'
    )
    for m in boolean_param_pattern.finditer(parameters_content):
        name, default, description = m.groups()
        parameters[name] = {
            'description': description,
            'default': True if default.lower() == 'true' else False,  # 真实的布尔值
            'required': False,
            'type': 'boolean'
        }

    # 匹配 choice 参数
    choice_param_pattern = re.compile(
        r'choice\s*\(\s*name\s*:\s*[\'"](\w+)[\'"]\s*,\s*choices\s*:\s*\[([^\]]+)\]\s*,\s*description\s*:\s*[\'"]([^\'"]*)[\'"]\s*\)'
    )
    for m in choice_param_pattern.finditer(parameters_content):
        name, choices, description = m.groups()
        # 处理 choices，去除引号和空格
        choices_list = [choice.strip().strip('\'"') for choice in choices.split(',')]
        parameters[name] = {
            'description': description,
            'default': choices_list[0] if choices_list else '',
            'required': False,
            'type': 'choice',
            'options': choices_list
        }

    # 检查是否有未处理的参数类型
    unsupported_param_pattern = re.compile(
        r'(\w+)Param\s*\('  # 匹配以Param结尾的参数类型
    )
    for m in unsupported_param_pattern.finditer(parameters_content):
        param_type = m.group(1) + 'Param'
        # logger.warning(f"Unsupported parameter type: {param_type}")
        if param_type not in ['stringParam', 'booleanParam', 'choiceParam', 'passwordParam', 'fileParam']:
            logger.warning(f"Unsupported parameter type: {param_type}")

    logger.info(f"Parameters Parsed:: {parameters}")
    return parameters


def generate_yaml(parameters: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    生成 GitHub Actions 的 parameters 字典。
    """
    inputs = {}
    for name, param in parameters.items():
        input_entry = {
            'description': param['description'],
            'required': param['required'],
            'type': param['type']
        }
        if param['type'] == 'choice':
            input_entry['options'] = param['options']
        if 'default' in param and param['default'] != '':
            input_entry['default'] = param['default']
        inputs[name] = input_entry

    # 使用 PlainScalarString 来表示 'on' 键，确保它不被引号包围
    yaml_content = {
        PlainScalarString('on'): {
            'workflow_dispatch': {
                'inputs': inputs
            }
        }
    }
    return yaml_content


def parameter_to_yaml(jenkinsfile_content: str) -> Dict[str, Any]:
    parameters = parse_parameters_block(jenkinsfile_content)
    if not parameters:
        logger.info("No parameters found in Jenkinsfile.groovy.")
        return parameters
    # 生成 YAML 字典
    github_actions_yaml_dict = generate_yaml(parameters)
    jenkins_comparison = JenkinsComparisonSingle()
    jenkins_comparison.add_comparison(yaml_to_string(github_actions_yaml_dict), 'parameters')
    return github_actions_yaml_dict


def main():
    # 读取 Jenkinsfile.groovy.groovy.groovy 内容
    try:
        with open('../Jenkinsfile.groovy', 'r') as f:
            jenkinsfile_content = f.read()
    except FileNotFoundError:
        logger.error("Jenkinsfile.groovy.groovy.groovy not found in the current directory.")
        return

    # 解析参数
    parameters = parse_parameters_block(jenkinsfile_content)

    if not parameters:
        print("No parameters found in Jenkinsfile.groovy.groovy.groovy.")
        return

    # 生成 YAML 字典
    github_actions_yaml_dict = generate_yaml(parameters)

    # 使用 ruamel.yaml 生成 YAML 字符串
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)

    # 写入文件
    with open('github_actions_parameters.yaml', 'w') as f:
        yaml.dump(github_actions_yaml_dict, f)

    # 输出结果
    print("Generated GitHub Actions Parameters YAML:")
    with open('github_actions_parameters.yaml', 'r') as f:
        print(f.read())
    print("Saved to github_actions_parameters.yaml")


if __name__ == "__main__":
    main()
