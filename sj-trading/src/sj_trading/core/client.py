import shioaji as sj
from .config import Config

class ShioajiClient:
    _instance = None
    _api = None
    _simulation = None  # Track the mode

    def __new__(cls, simulation: bool = True):
        if cls._instance is None:
            cls._instance = super(ShioajiClient, cls).__new__(cls)
            cls._instance._initialize(simulation)
            cls._simulation = simulation
        elif cls._simulation != simulation:
            raise RuntimeError(
                f"ShioajiClient already initialized with simulation={cls._simulation}. "
                f"Cannot reinitialize with simulation={simulation}."
            )
        return cls._instance

    def _initialize(self, simulation: bool):
        Config.validate(simulation)
        self._api = sj.Shioaji(simulation=simulation)
        self._api.login(
            api_key=Config.API_KEY,
            secret_key=Config.SECRET_KEY,
        )
        print(f"Shioaji logged in (Simulation: {simulation})")
        if not simulation:
             if Config.CA_CERT_PATH and Config.CA_PASSWORD:
                self._api.activate_ca(
                    ca_path=Config.CA_CERT_PATH,
                    ca_passwd=Config.CA_PASSWORD,
                    person_id=self._api.stock_account.person_id,
                )
        

    @property
    def api(self) -> sj.Shioaji:
        return self._api

    def bind_strategy(self, strategy):
        """
        Bind a strategy object to the client to receive events.
        The strategy object must implement methods like on_tick_fop_v1, on_quote_stk_v1 etc.
        """
        self._api.set_context(strategy)

    @classmethod
    def get_api(cls) -> sj.Shioaji:
        """Helper to get the underlying api object directly if instantiated."""
        if cls._instance is None:
             # Default to simulation if not initialized (or raise error depending on design)
             # Better to raise error or force init. Here we lazily init as sim for safety if not called before.
             cls(simulation=True)
        return cls._instance.api
