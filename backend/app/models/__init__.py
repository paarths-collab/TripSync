from app.models.user_model import User, College
from app.models.profile_model import Profile
from app.models.pooling_model import PoolingRequest, PoolingConnection, PoolingConnectionStatus
from app.models.message_model import Message
from app.models.conversation_model import Conversation
from app.models.service_model import ServicePost, ServiceApplication
from app.models.email_code_model import EmailCode, EmailCodePurpose
from app.models import campus_model  # noqa: F401  (registers the campus tables on Base.metadata)


def load_all_models() -> None:
    """Importing this package registers every table on Base.metadata.

    Call sites that need the full schema (create_all, Alembic, reset scripts) call
    this to make the dependency explicit.
    """
    return None
