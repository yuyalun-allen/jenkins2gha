import re
from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging

logger = setup_logging()


class ScriptPlugin(BasePlugin):
    def can_handle(self, step: dict) -> bool:
        return step.get('name') == 'script00'

    def parse_args(self, raw_args: str) -> dict:
        """
        解析 script 步骤的参数，拆分成单独的命令列表。
        """
        # 假设 raw_args 是多行命令
        commands = raw_args.strip().split('\n')
        return {'commands': commands}

    def convert(self, step: dict) -> list:
        """
        将 Jenkins 的 script 步骤转换为多个 GitHub Actions 步骤。
        """
        commands = step['args'].get('commands', [])
        logger.debug(f"ScriptPlugin: Retrieved commands='{commands}'")
        converted_steps = []

        for command in commands:
            command = command.strip()
            if not command:
                continue

            # 匹配环境变量设置，例如: env.VAR = value
            env_match = re.match(r'^env\.(\w+)\s*=\s*(.*)$', command)
            if env_match:
                var_name, var_value = env_match.groups()
                converted = {
                    'name': f"Set {var_name}",
                    'run': f'echo "{var_name}={var_value}" >> $GITHUB_ENV'
                }
                converted_steps.append(converted)
                logger.debug(f"ScriptPlugin: Converted env step='{converted}'")
                continue

            # 匹配 sh 命令，例如: sh "command" 或 sh 'command'
            sh_match = re.match(r'^sh\s+["\'](.*)["\']$', command)
            if sh_match:
                sh_command = sh_match.group(1)
                converted = {
                    'name': "Run Shell Command",
                    'run': sh_command
                }
                converted_steps.append(converted)
                logger.debug(f"ScriptPlugin: Converted sh step='{converted}'")
                continue

            # 如果无法解析，使用通用的 run 步骤
            converted = {
                'name': "Run Script Command",
                'run': command
            }
            converted_steps.append(converted)
            logger.debug(f"ScriptPlugin: Converted generic step='{converted}'")

        return converted_steps
