from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging
from converter.utils.map_jenkins_to_github_vars import map_jenkins_to_github_vars
logger = setup_logging()


class EchoPlugin(BasePlugin):
    def can_handle(self, step: dict) -> bool:
        return step.get('name') == 'echo'

    def parse_args(self, raw_args: str) -> dict:
        return {'message': raw_args}

    def convert(self, step: dict) -> list:
        message = step['args'].get('message', '')
        logger.debug(f"EchoPlugin: Retrieved message='{message}'")

        # 应用变量映射
        mapped_message = map_jenkins_to_github_vars(message)
        logger.debug(f"EchoPlugin: After variable mapping='{mapped_message}'")

        converted = {
            'name': 'Echo Message',
            'run':  f'echo "{mapped_message}"'
        }
        logger.debug(f"EchoPlugin: Converted step='{converted}'")
        return [converted]
