from team_schedule.api import parameters
from team_schedule.ics import service


@parameters("label")
def create_source(label):
    return service.create_source(label)


@parameters("source_id", "file_base64")
def preview(source_id, file_base64):
    return service.preview(source_id, file_base64)


@parameters("receipt", "source_id", "file_base64", "confirm", "resolutions")
def apply(receipt, source_id, file_base64, confirm, resolutions):
    return service.apply(receipt, source_id, file_base64, confirm, resolutions)
