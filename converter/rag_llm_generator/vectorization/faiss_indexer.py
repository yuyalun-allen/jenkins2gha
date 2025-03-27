import faiss
import os
from converter.utils.getLogger import setup_logging

logger = setup_logging()

# 存储向量的 FAISS 索引文件路径
# FAISS_INDEX_FILE = '../converter/rag_llm_generator/faiss_index/faiss_index.bin'
# 项目根目录（flask-jenkins2github_actions文件夹）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# 构建正确的索引文件路径
FAISS_INDEX_FILE = os.path.join(PROJECT_ROOT, 'faiss_index', 'faiss_index.bin')


# 创建 FAISS 索引并添加向量
def create_faiss_index(vectors):
    """
    创建 FAISS 索引并将向量添加到索引中。
    :param vectors: 向量列表
    :return: 返回 FAISS 索引对象
    """
    dimension = vectors.shape[1]  # 向量维度
    index = faiss.IndexFlatL2(dimension)  # 使用 L2 距离的索引
    index.add(vectors)  # 添加向量
    return index


# 保存 FAISS 索引到文件
def save_faiss_index(index):
    """
    将 FAISS 索引保存到文件。
    :param index: FAISS 索引对象
    """
    # 确保索引文件所在的目录存在
    directory = os.path.dirname(FAISS_INDEX_FILE)
    if not os.path.exists(directory):
        os.makedirs(directory)  # 创建目录

    faiss.write_index(index, FAISS_INDEX_FILE)
    logger.info(f"FAISS 索引已保存到 {FAISS_INDEX_FILE}")


# 加载 FAISS 索引
def load_faiss_index():
    """
    从文件加载 FAISS 索引。
    :return: 返回加载后的 FAISS 索引对象
    """
    if os.path.exists(FAISS_INDEX_FILE):
        index = faiss.read_index(FAISS_INDEX_FILE)
        return index
    else:
        # 添加调试信息
        logger.debug(f"项目根目录: {PROJECT_ROOT}")
        logger.debug(f"FAISS索引文件路径: {FAISS_INDEX_FILE}")
        logger.debug(f"FAISS index file {FAISS_INDEX_FILE} does not exist.")
        return None
