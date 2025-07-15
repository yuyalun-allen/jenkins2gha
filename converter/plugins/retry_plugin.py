from ruamel.yaml.scalarstring import PreservedScalarString, LiteralScalarString
import re
import textwrap
from typing import Dict, Any, List
from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def _format_script(max_retries: int, max_retries_expr: str, command: str) -> str:
    logger.debug(
        f"Formatting script with max_retries: {max_retries}, max_retries_expr: {max_retries_expr}, command: {command}")

    # 使用不带额外缩进的模板
    template = textwrap.dedent("""\
    retries=0
    {max_retries_line}
    success=false

    while [ $retries -lt $max_retries ]; do
        echo "Attempt $((retries + 1)) of $max_retries"
        {command} && success=true && break || success=false
        retries=$((retries + 1))

        if [ "$success" = true ]; then
            echo "Command succeeded!"
            break
        fi

        echo "Command failed, retrying..."
        sleep 2
    done

    if [ "$success" = false ]; then
        echo "Command failed after $max_retries attempts"
        exit 1
    fi
    """).strip()  # 移除首尾空行

    # 填充模板参数
    if max_retries_expr:
        max_retries_line = f"max_retries=${{{{ {max_retries_expr} }}}}"
    else:
        max_retries_line = f"max_retries={max_retries}"

    logger.debug(f"Formatted max_retries_line: {max_retries_line}")

    formatted_script = template.format(
        max_retries_line=max_retries_line,
        command=command
    )

    logger.debug(f"Formatted script: \n{formatted_script}")
    return formatted_script


def _extract_command(raw_block: str) -> str:
    logger.debug(f"Extracting command from raw block: {raw_block}")

    # 保持原有命令提取逻辑不变
    sh_pattern = re.compile(r"sh\s+['\"](.*?)['\"]", re.DOTALL)
    if sh_match := sh_pattern.search(raw_block):
        command = sh_match.group(1).strip()
        logger.debug(f"Found command in 'sh': {command}")
        return command

    script_pattern = re.compile(r"script\s*\{(.*?)\}", re.DOTALL)
    if script_match := script_pattern.search(raw_block):
        command = script_match.group(1).strip()
        logger.debug(f"Found command in 'script': {command}")
        return command

    logger.debug(f"No command found, returning raw block: {raw_block.strip()}")
    return raw_block.strip()


class RetryPlugin(BasePlugin):
    def can_handle(self, step: Dict[str, Any]) -> bool:
        logger.debug(f"Checking if step can be handled: {step}")
        return step.get('name') == 'retry'

    def parse_args(self, raw_args: str) -> Dict[str, Any]:
        logger.debug(f"Parsing arguments: {raw_args}")
        try:
            return {'max_retries': int(raw_args.strip())}
        except ValueError:
            logger.warning(f"Failed to parse {raw_args} as integer, using as expression")
            return {'max_retries_expr': raw_args.strip()}

    def convert(self, step: Dict[str, Any]) -> List[Dict[str, Any]]:
        logger.info(f"Converting step: {step}")

        args = step.get('args', {})
        raw_block = step.get('raw_block', '')
        command = _extract_command(raw_block)

        # 生成带正确格式的脚本
        script_content = _format_script(
            max_retries=args.get('max_retries', 3),
            max_retries_expr=args.get('max_retries_expr'),
            command=command
        )

        formatted_script = LiteralScalarString(script_content + '\n')

        # 输出最终生成的脚本内容
        logger.debug(f"Generated script content: \n{formatted_script}")

        # 使用PreservedScalarString保持多行格式
        result = [{
            'name': f'Retry command ({args.get("max_retries", 3)} attempts)' if not args.get('max_retries_expr')
            else 'Retry command with dynamic attempts',
            'id': f"retry_{abs(hash(command) % 1000)}",
            'run': formatted_script  # 保持多行字符串格式，避免加上 |-
        }]

        logger.info(f"Conversion result: {result}")
        return result
