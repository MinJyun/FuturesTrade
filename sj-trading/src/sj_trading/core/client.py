import shioaji as sj
from .config import Config

class ShioajiClient:
    _instance = None
    _api = None

    def __new__(cls, simulation: bool = True):
        if cls._instance is None:
            cls._instance = super(ShioajiClient, cls).__new__(cls)
            cls._instance._initialize(simulation)
        return cls._instance

    def _initialize(self, simulation: bool):
        Config.validate(simulation)
        self._api = sj.Shioaji(simulation=simulation)
        self._api.login(
            api_key=Config.API_KEY,
            secret_key=Config.SECRET_KEY,
        )
        
        if not simulation:
            self._api.activate_ca(
                ca_path=Config.CA_CERT_PATH,
                ca_passwd=Config.CA_PASSWORD,
            )
        print(f"Shioaji logged in (Simulation: {simulation})")

    @property
    def api(self) -> sj.Shioaji:
        return self._api

    @classmethod
    def get_api(cls) -> sj.Shioaji:
        """Helper to get the underlying api object directly if instantiated."""
        if cls._instance is None:
             # Default to simulation if not initialized (or raise error depending on design)
             # Better to raise error or force init. Here we lazily init as sim for safety if not called before.
             cls(simulation=True)
        return cls._instance.api
