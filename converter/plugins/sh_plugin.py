import re
from ruamel.yaml.scalarstring import LiteralScalarString, PlainScalarString
from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging
from converter.utils.map_jenkins_to_github_vars import map_jenkins_to_github_vars
logger = setup_logging()


def _clean_script(script: str) -> str:
    """清理脚本，规范化引号处理"""
    original = script
    script = script.strip()
    logger.debug(f"[Clean] Input: '{original}'")  # 输入日志

    # 处理三引号的情况
    if len(script) >= 6:
        if script.startswith("'''") and script.endswith("'''"):
            result = script[3:-3].strip()
            logger.debug(f"[Clean] Trimmed triple-single-quotes: '{result}'")
            return result
        if script.startswith('"""') and script.endswith('"""'):
            result = script[3:-3].strip()
            logger.debug(f"[Clean] Trimmed triple-double-quotes: '{result}'")
            return result

    # 处理单引号的情况
    if len(script) >= 2:
        if script[0] == "'" and script[-1] == "'":
            result = script[1:-1].strip()
            logger.debug(f"[Clean] Trimmed single-quotes: '{result}'")
            return result
        if script[0] == '"' and script[-1] == '"':
            result = script[1:-1].strip()
            logger.debug(f"[Clean] Trimmed double-quotes: '{result}'")
            return result

    logger.debug(f"[Clean] No quoting detected: '{script}'")
    return script


def _format_multiline_script(script: str) -> str:
    """格式化多行脚本，确保正确的缩进和换行"""
    logger.debug(f"[Format] Raw input:\n{script}")  # 原始输入

    # 处理共同缩进
    clean_multiline_script = clean_multiline_command(script)
    logger.debug(f"[Format] Clean Multiline output:\n{clean_multiline_script}")

    clean_multiline_script = remove_outer_quotes(clean_multiline_script)
    logger.debug(f"[Format] Final output:\n{clean_multiline_script}")

    return clean_multiline_script


def clean_multiline_command(text):
    """
    清理多行命令中的多余空格，保持每行的原始内容
    但移除每行开头和结尾的空白字符
    """
    # 按行分割文本
    lines = text.splitlines()

    # 对每行应用strip()去除前后空白
    cleaned_lines = [line.strip() for line in lines]

    # 移除空行
    cleaned_lines = [line for line in cleaned_lines if line]

    # 重新连接成多行文本
    result = "\n".join(cleaned_lines)

    return result


def remove_outer_quotes(text):
    """
    移除多行文本的外部引号并清理内容
    """
    # 去除首尾的单引号
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]

    # 分割成行
    lines = text.splitlines()

    # 移除空行
    non_empty_lines = [line for line in lines if line.strip()]

    # 重新组合文本
    cleaned_text = "\n".join(non_empty_lines)

    return cleaned_text


def _adjust_quote_style(script: str) -> str:
    """调整shell命令中的引号风格，主要针对echo命令"""
    # 检测是否为echo命令
    if not script.strip().startswith("echo "):
        return script

    # 提取echo后的内容
    content_start = script.find("echo") + 4
    content = script[content_start:].strip()

    # 检查内容是否被引号包围
    if content.startswith("'") and content.endswith("'"):
        # 提取单引号内的实际内容
        inner_content = content[1:-1]

        # 如果内容包含GitHub Actions变量引用(${{ ... }})，使用双引号
        if "${{" in inner_content:
            # 确保使用双引号包围内容，并处理可能的嵌套引号
            return f'echo "{inner_content}"'

    elif content.startswith('"') and content.endswith('"'):
        # 已经是双引号了，检查是否包含变量
        inner_content = content[1:-1]
        if "${{" in inner_content:
            # 已经是正确的格式，返回原样
            return script

    # 检查未被引号包围但包含GitHub变量的情况
    if "${{" in content and not (content.startswith('"') and content.endswith('"')):
        # 如果内容包含GitHub变量但没有使用双引号，添加双引号
        return f'echo "{content}"'

    return script


class ShPlugin(BasePlugin):
    def can_handle(self, step: dict) -> bool:
        return step.get('name') == 'sh'

    def parse_args(self, raw_args: str) -> dict:
        return {'script': raw_args}

    def convert(self, step: dict) -> list:
        script = step['args'].get('script', '')
        logger.debug(f"[Convert] Original script:\n{script}")

        cleaned_script = _clean_script(script)
        logger.debug(f"[Convert] After cleaning:\n{cleaned_script}")

        # 映射环境变量
        var_mapped_script = map_jenkins_to_github_vars(cleaned_script)
        logger.debug(f"[Convert] After variable mapping:\n{var_mapped_script}")

        # 调整引号风格
        final_script = _adjust_quote_style(var_mapped_script)
        logger.debug(f"[Convert] After quote adjustment:\n{final_script}")

        is_multiline = '\n' in final_script
        logger.debug(f"[Convert] Is multiline: {is_multiline}")

        if is_multiline:
            formatted_script = _format_multiline_script(final_script)
            run_value = LiteralScalarString(formatted_script)
            logger.debug("[Convert] Using LiteralScalarString for multiline")
        elif '"' in final_script:
            run_value = LiteralScalarString(final_script)
            logger.debug(f"[Convert] Using LiteralScalarString string: {run_value}")
        else:
            # 无特殊字符时使用普通字符串
            run_value = final_script
            logger.debug(f"[Convert] Using Formal Format")

        converted_step = {
            'name': 'Run Shell Command',
            'run': run_value
        }

        logger.debug("[Convert] Final YAML representation:")
        logger.debug("---")
        logger.debug(f"name: {converted_step['name']}")
        logger.debug(f"run: {converted_step['run']}")  # 模拟YAML输出，不使用竖线表示法
        logger.debug("---")

        return [converted_step]