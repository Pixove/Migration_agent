import samplelib.client
import samplelib.utils

from samplelib.old import OldModel


def create_model(config_path):
    config = samplelib.utils.load_config(config_path)
    client = samplelib.client.LegacyClient(config["endpoint"])
    return OldModel(client)
