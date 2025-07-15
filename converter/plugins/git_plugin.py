import re
from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging

logger = setup_logging()


class GitPlugin(BasePlugin):
    def can_handle(self, step: dict) -> bool:
        return step.get('name') == 'git'

    def parse_args(self, raw_args: str) -> dict:
        args_dict = {}
        try:
            if isinstance(raw_args, dict):
                args_dict = raw_args
                logger.debug(f"GitPlugin: Received args as dict: {args_dict}")
            elif isinstance(raw_args, str):
                logger.info(f"GitPlugin: Parsed raw_args: {raw_args}")
                # 处理键值对参数
                key_value_pattern = re.compile(r'(\w+)\s*:\s*[\'"]([^\'"]+)[\'"]')
                for match in key_value_pattern.finditer(raw_args):
                    key, value = match.groups()
                    args_dict[key] = value
                    logger.debug(f"Parsed key-value arg: {key} = {value}")

                # 如果没有找到键值对，检查是否为纯URL
                if not args_dict:
                    trimmed_raw = raw_args.strip().strip('\'"')
                    # 匹配常见Git仓库URL格式
                    url_pattern = re.compile(
                        r'^(https?://|git@)(github\.com|gitee\.com)[/:][^\s/]+/[^\s/]+?$',
                        re.IGNORECASE
                    )
                    if url_pattern.match(trimmed_raw):
                        args_dict['url'] = trimmed_raw
                        logger.debug(f"Parsed raw_args as URL: {trimmed_raw}")

                logger.debug(f"GitPlugin: Parsed args='{args_dict}'")
            else:
                logger.error(f"GitPlugin: Unsupported type for raw_args: {type(raw_args)}")
        except Exception as e:
            logger.error(f"GitPlugin: Failed to parse args '{raw_args}' - {e}")
        return args_dict

    def convert(self, step: dict) -> list:
        args = step.get('args', {})
        url = args.get('url', '')
        branch = args.get('branch', 'main')
        credentials_id = args.get('credentialsId', '')

        token = "${{ secrets.GITHUB_TOKEN }}" if not credentials_id else f"${{{{ secrets.{credentials_id} }}}}"

        # 扩展URL匹配规则以支持更多格式
        url_match = re.match(
            r'https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+)(\.git)?',
            url,
            re.IGNORECASE
        )
        if url_match:
            repository = f"{url_match.group('owner')}/{url_match.group('repo')}"
        else:
            repository = url  # 保留原始URL用于私有仓库或其他格式

        converted = {
            'name': 'Checkout Repository',
            'uses': 'actions/checkout@v3',
            'with': {
                'repository': repository,
                'ref': branch,
                'token': token
            }
        }
        logger.debug(f"GitPlugin: Converted step='{converted}'")
        return [converted]