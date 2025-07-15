import re
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def map_jenkins_to_github_vars(script: str) -> str:
    """将Jenkins环境变量映射到GitHub Actions环境变量

    Args:
        script (str): 包含Jenkins环境变量的脚本或消息

    Returns:
        str: 转换后的脚本，Jenkins变量被替换为对应的GitHub Actions变量
    """
    # 变量映射表
    var_mapping = {
        "BUILD_NUMBER": "github.run_number",
        "JOB_NAME": "github.workflow",
        "WORKSPACE": "github.workspace",
        "BUILD_ID": "github.run_id",
        "JENKINS_URL": "github.server_url",
        # 可以添加更多的变量映射
    }

    logger.debug(f"[VariableMapper] Input script: {script}")

    # 使用正则表达式查找所有${VAR}格式的变量
    pattern = re.compile(r'\${([A-Za-z_][A-Za-z0-9_]*)}')

    def replace_var(match):
        var_name = match.group(1)
        if var_name in var_mapping:
            replacement = f"${{{{ {var_mapping[var_name]} }}}}"  # 注意这里使用双大括号来生成单大括号
            logger.debug(f"[VariableMapper] Replacing ${{{var_name}}} with {replacement}")
            return replacement
        logger.debug(f"[VariableMapper] Variable ${{{var_name}}} not found in mapping, keeping as is")
        return match.group(0)  # 如果未知变量，保持原样

    result = pattern.sub(replace_var, script)
    logger.debug(f"[VariableMapper] Output script: {result}")
    return result
