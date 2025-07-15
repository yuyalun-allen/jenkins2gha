from converter.utils.getLogger import setup_logging


logger = setup_logging()

logger.info("正在加载向量化模型: sentence_transformers")
from sentence_transformers import SentenceTransformer
logger.info("成功加载向量化模型: sentence_transformers")
# 初始化模型
logger.info("正在初始化模型: all-MiniLM-L6-v2")
model = SentenceTransformer('all-MiniLM-L6-v2')
# model = SentenceTransformer(r'C:\Users\Lenovo\.cache\huggingface\hub\models--sentence-transformers--all-MiniLM-L6-v2'
#                             r'\snapshots\fa97f6e7cb1a59073dff9e6b13e2715cf7475ac9')
# model = SentenceTransformer(r'C:\Users\han\.cache\huggingface\hub\models--sentence-transformers--all-MiniLM-L6-v2\snapshots\fa97f6e7cb1a59073dff9e6b13e2715cf7475ac9')
# C:\Users\han\.cache\huggingface\hub\models--sentence-transformers--all-MiniLM-L6-v2\snapshots\fa97f6e7cb1a59073dff9e6b13e2715cf7475ac9
logger.info("成功初始化模型: all-MiniLM-L6-v2")


# 向量化文本
def vectorize_text(texts):
    """
    将一组文本转换为向量。
    :param texts: 文本列表
    :return: 对应的向量列表
    """
    vectors = model.encode(texts, show_progress_bar=True)
    return vectors
