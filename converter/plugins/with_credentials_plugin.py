import re
from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging


logger = setup_logging()


class WithCredentialsPlugin(BasePlugin):
    def can_handle(self, step: dict) -> bool:
        return step.get('name') == 'withCredentials00'

    def parse_args(self, raw_args: str) -> dict:
        """
        解析 withCredentials 的参数。
        例如:
        [usernamePassword(credentialsId: 'docker-registry-credentials', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]
        返回:
        {
            'credentials': [
                {
                    'type': 'usernamePassword',
                    'credentialsId': 'docker-registry-credentials',
                    'usernameVariable': 'DOCKER_USER',
                    'passwordVariable': 'DOCKER_PASS'
                }
            ]
        }
        """
        credentials = []
        # 匹配 usernamePassword 类型
        pattern = re.compile(r'(\w+)\s*\(\s*credentialsId\s*:\s*[\'"]([^\'"]+)[\'"],\s*usernameVariable\s*:\s*[\'"]([^\'"]+)[\'"],\s*passwordVariable\s*:\s*[\'"]([^\'"]+)[\'"]\s*\)')
        matches = pattern.findall(raw_args)
        for match in matches:
            cred_type, credentialsId, usernameVariable, passwordVariable = match
            credentials.append({
                'type': cred_type,
                'credentialsId': credentialsId,
                'usernameVariable': usernameVariable,
                'passwordVariable': passwordVariable
            })
        return {'credentials': credentials}

    def convert(self, step: dict) -> list:
        """
        将 Jenkins 的 withCredentials 步骤转换为 GitHub Actions 的认证步骤。
        """
        parsed_args = step['args']
        credentials = parsed_args.get('credentials', [])
        raw_block = step.get('raw_block', '')
        logger.debug(f"WithCredentialsPlugin: Retrieved credentials='{credentials}', block='{raw_block}'")

        converted_steps = []
        for cred in credentials:
            cred_id = cred.get('credentialsId', '')
            username_var = cred.get('usernameVariable', '')
            password_var = cred.get('passwordVariable', '')

            # 转换为 GitHub Secrets
            # 假设 credentialsId 对应 GitHub 的 secret，名称为 cred_id
            # 可以根据需求调整
            converted_steps.append({
                'name': f"Set {username_var} and {password_var} Secrets",
                'env': {
                    username_var: f"${{ secrets.{cred_id}_USERNAME }}",
                    password_var: f"${{ secrets.{cred_id}_PASSWORD }}"
                }
            })

        # 解析 raw_block 中的命令，并转换为步骤
        # 可以使用现有的插件或通用转换逻辑
        # 这里假设 raw_block 包含 sh 命令，使用现有的 ScriptPlugin 或通用逻辑处理
        # 例如，使用 ScriptPlugin 的转换逻辑
        # 此处简化处理，直接将 raw_block 作为单独的 run 步骤
        if raw_block:
            converted_steps.append({
                'name': "Run Commands within withCredentials",
                'run': raw_block
            })

        logger.debug(f"WithCredentialsPlugin: Converted steps='{converted_steps}'")
        return converted_steps
