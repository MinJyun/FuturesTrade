import os
import shioaji as sj

def login_shioaji(simulation: bool = True):
    """
    登入 Shioaji API。

    Args:
        simulation (bool, optional): 是否使用模擬環境. Defaults to True.

    Returns:
        shioaji.Shioaji: 已登入的 API 物件。
    """
    api = sj.Shioaji(simulation=simulation)
    api.login(
        api_key=os.environ["API_KEY"],
        secret_key=os.environ["SECRET_KEY"],
    )
    
    # 只有在需要下單時才啟用 CA
    if not simulation:
        api.activate_ca(
            ca_path=os.environ["CA_CERT_PATH"],
            ca_passwd=os.environ["CA_PASSWORD"],
        )
        
    return api
