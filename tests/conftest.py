import pytest 
from airflow.models import DagBag

@pytest.fixture
def dagbag():
    return DagBag()
