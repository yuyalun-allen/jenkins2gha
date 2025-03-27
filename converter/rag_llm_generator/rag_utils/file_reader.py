import os

# 插件数据存储目录
plugin_data_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'jenkins_plugins_2025')


# 读取插件数据文件
def read_plugin_data():
    plugin_descriptions = []
    for filename in os.listdir(plugin_data_directory):
        if filename.endswith('.txt'):
            file_path = os.path.join(plugin_data_directory, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read().strip()  # 读取文件内容并去除首尾空白
                plugin_descriptions.append(content)  # 将内容作为向量直接存储
    return plugin_descriptions


# 处理插件数据并返回所有描述
def process_plugin_data():
    return read_plugin_data()
