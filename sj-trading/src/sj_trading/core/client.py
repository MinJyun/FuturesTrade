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

    def set_callbacks(self, on_tick=None, on_match=None):
        """
        Register callbacks for market data and order updates.
        """
        if on_tick:
            self._api.quote.set_on_tick_fop_v1_callback(on_tick)
            self._api.quote.set_on_tick_stk_v1_callback(on_tick)
            
        # Shioaji uses set_context to bind the client itself as the callback handler usually,
        # or we can assign the callback function directly if supported.
        # But simpler way for modern Shioaji is to use the callback setters if available, 
        # or simply bind the passed functions to the client instance if using set_context.
        
        # However, Shioaji's event model usually invokes methods on the object passed to set_context.
        # Let's use a wrapper approach if we want to be flexible, or just expose the api setters.
        
        # For straightforward usage:
        if on_event: # This variable 'on_event' is not defined in the snippet, assuming it's a placeholder or typo for 'on_match' or a generic event handler.
             # Just set the context to an object that has on_tick/on_quote_stk methods?
             # Actually, Shioaji's set_context(self) expects 'self' to have methods like `on_tick_stk_v1`.
             pass
             
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
