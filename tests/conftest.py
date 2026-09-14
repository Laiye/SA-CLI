import pytest

from tests.fakes import FakeResourceManager, FakeVisaResource

@pytest.fixture
def fake_resource():
    return FakeVisaResource()


@pytest.fixture
def fake_rm(fake_resource):
    return FakeResourceManager(fake_resource)
