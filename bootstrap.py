from fusion_backend.core import Core
import time
import logging

logging.basicConfig(level=logging.WARNING)

if __name__ == '__main__':
    # 加载配置文件
    manager = Core('config.json')

    manager.load()
    manager.run()
    while True:
        time.sleep(1)


