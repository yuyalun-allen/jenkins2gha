from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BasePlugin(ABC):
    @abstractmethod
    def can_handle(self, step: Dict[str, Any]) -> bool:
        """
        判断当前步骤是否由该插件处理
        """
        pass

    @abstractmethod
    def convert(self, step: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        转换步骤为 GitHub Actions 步骤
        """
        pass

    def parse_args(self, raw_args: str) -> Dict[str, Any]:
        """
        解析原始参数，返回结构化的参数字典。
        默认实现仅返回 raw_args，具体插件可以重写此方法。
        """
        return {'raw_args': raw_args}
