from fusion_backend.core import Core

if __name__ == '__main__':
    # 加载配置文件
    manager = Core('config.json')

    manager.load()
    manager.run()

