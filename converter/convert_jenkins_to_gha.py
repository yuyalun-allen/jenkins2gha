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


def convert_jenkins_to_actions_string(jenkins_content):
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
    components = [env_component, param_component, post_component, stage_component, tool_component, trigger_component]
    merged_workflow = merge_yaml_components(components)
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


def main():
    # 读取 Jenkinsfile.groovy 内容
    try:
        with open('Jenkinsfile2.groovy', 'r', encoding='utf-8') as f:
            jenkinsfile_content = f.read()
    except FileNotFoundError:
        try:
            # 检查父目录
            with open('../Jenkinsfile.groovy', 'r') as f:
                jenkinsfile_content = f.read()
        except FileNotFoundError:
            logger.error("Jenkinsfile.groovy not found in the current directory or parent directory.")
            return
    str = convert_jenkins_to_actions_string(jenkins_content=jenkinsfile_content)
    logger.info(f"str : {str}")


if __name__ == "__main__":
    main()
