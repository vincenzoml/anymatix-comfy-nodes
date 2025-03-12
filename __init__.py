import sys
import asyncio
from .fetch import delete_files
from .expunge import *
import json
from typing import Dict
import app.logger
import folder_paths
from aiohttp import web
import os
import socket
from server import PromptServer
import app

from .anymatix_checkpoint_fetcher import (
    AnymatixCheckpointFetcher,
    AnymatixCheckpointLoader,
    AnymatixFetcher,
    AnymatixLoraLoader,
    AnymatixUpscaleModelLoader,
    AnymatixCLIPLoader,
    AnymatixUNETLoader,
    AnymatixVAELoader,
    AnymatixCLIPVisionLoader,
)
from .anymatix_image_save import Anymatix_Image_Save
from .anymatix_maskimage import AnymatixMaskImage

NODE_CLASS_MAPPINGS = {
    "AnymatixCheckpointFetcher": AnymatixCheckpointFetcher,
    "AnymatixCheckpointLoader": AnymatixCheckpointLoader,
    "AnymatixLoraLoader": AnymatixLoraLoader,
    "AnymatixFetcher": AnymatixFetcher,
    "AnymatixImageSave": Anymatix_Image_Save,
    "AnymatixUpscaleModelLoader": AnymatixUpscaleModelLoader,
    "AnymatixMaskImage": AnymatixMaskImage,
    "AnymatixCLIPLoader": AnymatixCLIPLoader,
    "AnymatixUNETLoader": AnymatixUNETLoader,
    "AnymatixVAELoader": AnymatixVAELoader,
    "AnymatixCLIPVisionLoader": AnymatixCLIPVisionLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AnymatixCheckpointFetcher": "Anymatix Checkpoint Fetcher",
    "AnymatixCheckpointLoader": "Anymatix Checkpoint Loader",
    "AnymatixFetcher": "Anymatix Fetcher",
    "AnymatixLoraLoader": "Anymatix Lora Loader",
    "AnymatixImageSave": "Anymatix Image Save",
    "AnymatixUpscaleModelLoader": "Anymatix Upscale Model Loader",
    "AnymatixMaskImage": "Anymatix Mask Image",
    "AnymatixCLIPLoader": "Anymatix CLIP Loader",
    "AnymatixUNETLoader": "Anymatix UNET Loader",
    "AnymatixVAELoader": "Anymatix VAE Loader",
    "AnymatixCLIPVisionLoader": "Anymatix CLIP Vision Loader",
}


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

print(f"anymatix: running on host {socket.gethostname()}")
allowed_dirs = ["output", "input", "models"]

routes = PromptServer.instance.routes


@routes.get("/anymatix/log")
async def get_log(request):
    return web.json_response(list(app.logger.get_logs()))


@routes.post("/anymatix/uploadAsset")
async def upload_asset(request):
    reader = await request.multipart()

    hash_value = None
    file_extension = None

    # Iterate over the parts in the multipart form
    async for part in reader:
        if part.name == "hash":  # Retrieve the 'hash' field
            hash_value = await part.text()
        elif part.name == "extension":  # Retrieve the 'extension' field
            file_extension = await part.text()
        elif part.name == "file":  # Handle the file upload
            file_path = os.path.join(
                folder_paths.input_directory, f"{hash_value}.{file_extension}"
            )
            with open(file_path, "wb") as output_file:
                while chunk := await part.read_chunk():  # Read file in chunks
                    output_file.write(chunk)
    # TODO: choose a temporary file name first, then check file hash, then rename

    # This is done from the client in js:
    # const formData = new FormData()
    # formData.append('file', file)
    # formData.append('hash', h)
    # file = data.get('file')

    # if not file:
    #     return web.Response(status=400, text="File is required")

    # extension = data.get('extension')
    # if not extension:
    #     return web.Response(status=400, text="extension is required")

    # import hashlib

    # # Compute the SHA256 hash of the file
    # file_hash = hashlib.sha256()
    # while True:
    #     chunk = file.read(8192)
    #     if not chunk:
    #         break
    #     file_hash.update(chunk)
    # hash_value = file_hash.hexdigest()

    # file_path = os.path.join(
    #     folder_paths.input_directory, f"{hash_value}.{extension}")

    # with open(file_path, 'wb') as f:
    #     file.seek(0)
    #     while True:
    #         chunk = file.read(8192)
    #         if not chunk:
    #             break
    #         f.write(chunk)

    return web.Response(status=200)


outdir = f"{folder_paths.output_directory}/anymatix/results"
os.makedirs(outdir, exist_ok=True)


@routes.get("/anymatix/reboot")
async def serve_reboot(request):
    print("anymatix: rebooting")

    # Schedule the reboot asynchronously
    # Delay of 2 seconds (adjust as needed)
    asyncio.create_task(reboot_after_delay(2))

    # Return the response immediately
    return web.Response(status=200)


async def reboot_after_delay(delay: int):
    await asyncio.sleep(delay)
    os.execv(sys.executable, [sys.executable] + sys.argv)


@routes.post("/anymatix/expunge")
async def serve_expunge(request):
    print("anymatix: expunging cache")
    data = await request.json()
    keep: list[str] = data["keep"]
    await expunge(keep, outdir)
    return web.Response(status=200)


@routes.get("/anymatix/cache_size")
async def serve_cache_size(request):
    result = await count_outputs(outdir)
    return web.json_response(result)


@routes.post("/anymatix/delete_resource")
async def serve_delete(request):
    print("anymatix: deleting resource")
    data = await request.json()
    print("anymatix:", data)
    url = data["url"]
    delete_files(url, folder_paths.models_dir)
    return web.Response(status=200)


@routes.get("/anymatix/{basedir}/{filename:.+}")
async def serve_file(request):
    response = web.Response(text="File not found", status=404)

    # TODO: check also dirmap in anymatix_checkpoint_fetcher, reconcile that with "allowed_dirs"
    basedir = request.match_info["basedir"]

    if basedir in allowed_dirs:
        # TODO: the check on getcwd is plain wrong (if the cwd is not what I expected). Determine from the current script?
        file_path = os.path.abspath(f"{basedir}/{request.match_info['filename']}")
        base = f"{os.path.abspath(os.getcwd())}/{basedir}"
        if (
            file_path.startswith(base)
            and os.path.isfile(file_path)
            and os.access(file_path, os.R_OK)
        ):
            response = web.FileResponse(file_path)
        # else:
        #     print("****** anymatix", file_path, "is not allowed or does not exist", os.getcwd())

    return response


# resource_extensions = [".ckpt", ".safetensors"]


@routes.get("/anymatix/resources")
async def serve_resources(_request):
    json_files = (
        os.path.join(dirpath, filename)
        for dirpath, _, filenames in os.walk(folder_paths.models_dir)
        for filename in filenames
        if filename.endswith(".json")
    )

    def get_json_data(path: str) -> dict:
        with open(path, "r") as f:
            return json.load(f)

    def get_type(path: str) -> str:
        return path.removeprefix(folder_paths.models_dir).split(os.sep)[1]

    def get_contents(path: str):
        data = get_json_data(path)
        type = get_type(path)
        file_path = path.removeprefix(os.path.join(folder_paths.models_dir, type))
        return (data, type, file_path)

    contents = map(get_contents, json_files)

    result: Dict[str, list] = {}

    for data, type, file_path in contents:
        if type in result:
            result[type].append(data)
        else:
            result[type] = [data]

    return web.json_response(result)
