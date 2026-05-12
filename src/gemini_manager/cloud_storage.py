from abc import ABC, abstractmethod
from typing import List, Optional

class CloudFile:
    def __init__(self, name, size, last_modified):
        self.name = name
        self.size = size
        self.last_modified = last_modified

class CloudStorageProvider(ABC):
    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str):
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str):
        pass

    @abstractmethod
    def list_files(self, prefix: str = "") -> List[CloudFile]:
        pass

    @abstractmethod
    def delete_file(self, remote_path: str):
        pass

    @abstractmethod
    def upload_string(self, data_str: str, remote_path: str):
        pass

    @abstractmethod
    def download_to_string(self, remote_path: str) -> Optional[str]:
        pass
