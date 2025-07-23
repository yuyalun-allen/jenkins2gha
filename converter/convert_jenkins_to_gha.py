from argparse import ArgumentParser
from typing import Dict, Any
from ruamel.yaml import YAML
from converter.utils.getLogger import setup_logging
from converter.utils.merge_yaml_components import merge_yaml_components
from converter.utils.strip_jenkins_comments import remove_groovy_comments
from converter.parse.parse_environment import environment_to_yaml
from converter.parse.parse_parameter import parameter_to_yaml
from converter.parse.parse_option import option_to_yaml
from converter.parse.parse_post import post_to_yaml
from converter.parse.parse_stage import stage_to_yaml
from converter.parse.parse_tool import tool_to_yaml
from converter.parse.parse_trigger import trigger_to_yaml
from converter.utils.yaml_to_string import yaml_to_string
from converter.utils.analyze_jenkins_dependencies import analyze_jenkins_dependencies
from converter.utils.JenkinsComparisonSingle import JenkinsComparisonSingle
logger = setup_logging()


def convert_jenkins_to_actions_string(jenkins_content, silent):
    """
    将Jenkins配置文件内容转换为GitHub Actions工作流配置

    Args:
        jenkins_content (str): Jenkins配置文件内容

    Returns:
        str: GitHub Actions工作流YAML内容
    """
    jenkins_comparison = JenkinsComparisonSingle()
    jenkins_comparison.set_jenkinsfile_content(jenkins_content)
    dependencies = analyze_jenkins_dependencies(jenkins_content)

    remove_groovy_comments_jenkinsfile_content = remove_groovy_comments(jenkins_content)
    env_component = environment_to_yaml(remove_groovy_comments_jenkinsfile_content)
    logger.info(f"env: {env_component}")

    trigger_component = trigger_to_yaml(remove_groovy_comments_jenkinsfile_content)
    logger.info(f"trigger: {trigger_component}")

    param_component = parameter_to_yaml(remove_groovy_comments_jenkinsfile_content)
    logger.info(f"parameter: {param_component}")

    option_component = option_to_yaml(remove_groovy_comments_jenkinsfile_content)
    logger.info(f"option: {option_component}")

    post_component = post_to_yaml(remove_groovy_comments_jenkinsfile_content, dependencies)
    logger.info(f"post: {post_component}")

    tool_component = tool_to_yaml(remove_groovy_comments_jenkinsfile_content)
    logger.info(f"tool: {tool_component}")

    stage_component = stage_to_yaml(remove_groovy_comments_jenkinsfile_content, option_component, dependencies)
    logger.info(f"stages: {stage_component}")

    # 合并组件
    components = [env_component, param_component, stage_component, post_component, tool_component, trigger_component]
    merged_workflow = merge_yaml_components(components)
    if silent:
        merged_workflow = remove_notes_field(merged_workflow)

    logger.info(f"merged_workflow: {merged_workflow}")

    # # 输出到文件
    # yaml = YAML()
    # yaml.default_flow_style = False
    # yaml.indent(mapping=2, sequence=4, offset=2)
    # with open('github-workflow.yml', 'w') as f:
    #     yaml.dump(merged_workflow, f)
    result = {'actions_file_content': yaml_to_string(merged_workflow)}
    logger.info("已生成GitHub Actions工作流文件: github-workflow.yml")
    logger.info(f"github-workflow.yml:\n{result['actions_file_content']}")

    result['detailed_comparison'] = jenkins_comparison.get_comparison()
    jenkins_comparison.clear()
    return result

def remove_notes_field(yaml_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    递归删除YAML字典中的notes字段
    
    Args:
        yaml_dict: 要处理的YAML字典
        
    Returns:
        Dict[str, Any]: 删除notes字段后的YAML字典
    """
    if not isinstance(yaml_dict, dict):
        return yaml_dict
    
    # 创建新字典，避免修改原字典
    result = {}
    
    for key, value in yaml_dict.items():
        # 跳过notes字段
        if key == 'notes':
            continue
            
        if isinstance(value, dict):
            # 递归处理字典
            result[key] = remove_notes_field(value)
        elif isinstance(value, list):
            # 处理列表中的字典元素
            result[key] = []
            for item in value:
                if isinstance(item, dict):
                    result[key].append(remove_notes_field(item))
                else:
                    result[key].append(item)
        else:
            # 保留其他类型的值
            result[key] = value
    
    return result

def main():
    # parser = ArgumentParser(description="Jenkinsfile 转化为 CodeArts 的 yml")
    # parser.add_argument('--input-file', '-i', type=str, required=True, help='输入 Jenkinsfille 文件的路径')
    # parser.add_argument('--output-file', '-o',  type=str, required=True, help='输出 CodeArts yml 文件的路径')
    # parser.add_argument('--silent', '-s', action='store_true', help='不生成 notes 字段')
    #
    # args = parser.parse_args()

    # 读取 Jenkinsfile.groovy 内容
    with open("../example/input/JenkinsFile.yml", 'r', encoding='utf-8') as f:
        jenkinsfile_content = f.read()

    yml_dict = convert_jenkins_to_actions_string(jenkins_content=jenkinsfile_content, silent=True)
    logger.info(f"str : {str}")

    with open("../example/output/codeArtsPipeline.yml", 'w', encoding='utf-8') as f:
        f.write(yml_dict['actions_file_content'])


if __name__ == "__main__":
    main()

