import os
import importlib
from typing import Dict
from converter.plugins.base_plugin import BasePlugin
from converter.utils.getLogger import setup_logging

logger = setup_logging()


def load_plugins(plugin_dir: str) -> Dict[str, BasePlugin]:
    plugins = {}
    try:
        # 尝试确定绝对路径
        app_root = os.path.abspath(os.path.dirname(__file__))
        full_plugin_path = os.path.join(app_root, '..', plugin_dir)

        # 检查目录是否存在
        if not os.path.exists(full_plugin_path):
            logger.warning(f"插件目录不存在: {full_plugin_path}，使用空插件列表")
            return {}

        logger.info(f"正在加载插件，目录: {full_plugin_path}")
        for filename in os.listdir(full_plugin_path):
            if filename.endswith('.py') and filename not in ['__init__.py', 'base_plugin.py']:
                try:
                    module_name = filename[:-3]
                    logger.info(f"尝试导入插件: {module_name}")
                    # 尝试正确的导入路径
                    module = importlib.import_module(f'converter.plugins.{module_name}')

                    for attribute in dir(module):
                        try:
                            cls = getattr(module, attribute)
                            if isinstance(cls, type) and issubclass(cls, BasePlugin) and cls is not BasePlugin:
                                plugin_instance = cls()
                                plugins[module_name] = plugin_instance
                                logger.info(f"成功加载插件: {module_name}")
                        except Exception as attr_err:
                            logger.error(f"处理插件属性时出错: {str(attr_err)}")
                except Exception as mod_err:
                    logger.error(f"导入插件模块时出错: {str(mod_err)}")

        return plugins
    except Exception as e:
        logger.error(f"加载插件过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}  # 出错时返回空字典
