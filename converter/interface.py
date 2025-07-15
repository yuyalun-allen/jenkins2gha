from converter.convert_jenkins_to_gha import convert_jenkins_to_actions_string


def convert_jenkins_to_actions(jenkins_content):
    """
    将Jenkins配置文件内容转换为GitHub Actions工作流配置

    Args:
        jenkins_content (str): Jenkins配置文件内容

    Returns:
        str: GitHub Actions工作流YAML内容
    """
    result = convert_jenkins_to_actions_string(jenkins_content)
    return result
