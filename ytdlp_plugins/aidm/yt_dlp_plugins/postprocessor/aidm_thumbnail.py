"""Optional artwork only: yt-dlp still owns extraction, transfer and tagging.

Loaded explicitly by youtube.py. Keep this module independent of AiDM imports
so the installed yt-dlp executable (including its zip distribution) can load it.
"""

from copy import deepcopy
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from yt_dlp.dependencies import mutagen
from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import RequestError
from yt_dlp.postprocessor.embedthumbnail import EmbedThumbnailPP
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor, FFmpegThumbnailsConvertorPP
from yt_dlp.utils import PostProcessingError, determine_ext

ARTWORK_ERRORS = (PostProcessingError, OSError, ValueError)
if mutagen:
    ARTWORK_ERRORS += (mutagen.MutagenError,)


class AiDMThumbnailPP(FFmpegPostProcessor):
    """Tag a disposable copy, then atomically replace the completed audio."""

    SUPPORTED = frozenset(('mp3', 'flac', 'm4a', 'mp4', 'm4v', 'mov',
                           'ogg', 'opus', 'mkv', 'mka'))

    def __init__(self, downloader=None, telemetry='false'):
        super().__init__(downloader)
        self.telemetry = telemetry == 'true'

    def artwork_warning(self, reason):
        self.report_warning(f'Optional artwork skipped: {reason}. Audio preserved.')
        # A bounded, fixed record; never parse arbitrary downloader warnings.
        if self.telemetry:
            self.to_screen('AIDM_ARTWORK_WARNING:skipped', prefix=False)

    def download_thumbnail(self, info, directory):
        # yt-dlp orders thumbnails from least to most preferred. Each invocation
        # receives this video's info, so bulk items cannot share the wrong cover.
        for thumbnail in reversed(info.get('thumbnails') or []):
            url = thumbnail.get('url')
            if not url:
                continue
            extension = determine_ext(url, 'jpg')
            if extension not in {'jpg', 'jpeg', 'png', 'webp', 'avif', 'gif'}:
                extension = 'jpg'
            target = Path(directory) / ('cover.' + extension)
            try:
                headers = dict(info.get('http_headers') or {})
                headers.update(thumbnail.get('http_headers') or {})
                with self._downloader.urlopen(Request(url, headers=headers)) as response:
                    with target.open('wb') as output:
                        shutil.copyfileobj(response, output)
                return str(target)
            except RequestError:
                continue
        raise PostProcessingError('no thumbnail could be downloaded')

    def run(self, info):
        if info['ext'] not in self.SUPPORTED:
            self.artwork_warning(f"the original {info['ext']} container does not support cover artwork")
            return [], info
        filename = Path(info['filepath'])
        try:
            # Same filesystem permits atomic replacement. The original stays
            # playable through tagging failures, cancellation and disk errors.
            with TemporaryDirectory(prefix='.aidm-artwork-', dir=filename.parent) as directory:
                thumbnail = self.download_thumbnail(info, directory)
                # Decode even JPG/PNG inputs: some tagging paths accept invalid
                # image bytes without reporting an error. FFmpeg validates them.
                converter = FFmpegThumbnailsConvertorPP(self._downloader)
                validated = str(Path(directory) / 'validated.png')
                converter.run_ffmpeg(thumbnail, validated, ['-frames:v', '1', '-update', '1'])
                working = Path(directory) / filename.name
                shutil.copy2(filename, working)
                tagged = deepcopy(info)
                tagged['filepath'] = str(working)
                tagged['thumbnails'] = [{'filepath': validated}]
                tagged['__files_to_move'] = {}
                if info['ext'] == 'flac' and not mutagen:
                    # yt-dlp's FLAC tagger requires optional Mutagen, which is
                    # absent from some standalone builds. FFmpeg can write the
                    # same picture block with stream copy; no extra dependency.
                    tagged_file = str(Path(directory) / 'tagged.flac')
                    self.run_ffmpeg_multiple_files(
                        [str(working), validated], tagged_file,
                        ['-map', '0:a', '-map', '1:v', '-c', 'copy',
                         '-disposition:v:0', 'attached_pic',
                         '-metadata:s:v', 'title=Album cover',
                         '-metadata:s:v', 'comment=Cover (front)'])
                    os.replace(tagged_file, working)
                else:
                    EmbedThumbnailPP(self._downloader).run(tagged)
                streams = self.get_metadata_object(str(working)).get('streams', [])
                if not any(stream.get('disposition', {}).get('attached_pic') for stream in streams):
                    raise PostProcessingError('embedded cover could not be verified')
                os.replace(working, filename)
        except ARTWORK_ERRORS as error:
            self.artwork_warning(str(error))
        return [], info
