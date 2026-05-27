import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from config import settings

_motor_client: AsyncIOMotorClient | None = None


def get_collection(name: str):
    return _motor_client[settings.db_name][name]


async def init_db():
    global _motor_client
    _motor_client = AsyncIOMotorClient(
        settings.mongodb_uri,
        tlsCAFile=certifi.where(),
    )
    await init_beanie(
        database=_motor_client[settings.db_name],
        document_models=[
            "models.question.Question",
        ],
    )
