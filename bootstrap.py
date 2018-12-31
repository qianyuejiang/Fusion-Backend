from fusion_backend.config import Config

from shadowsocks.server import main

if __name__ == '__main__':
    # 加载配置文件
    config = Config('config.json')

    config.load()
    # print("done")

