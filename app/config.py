from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    alchemy_api_key: str = ""
    helius_api_key: str = ""

    @property
    def base_rpc_url(self) -> str:
        return f"https://base-mainnet.g.alchemy.com/v2/{self.alchemy_api_key}"

    @property
    def solana_rpc_url(self) -> str:
        return f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
