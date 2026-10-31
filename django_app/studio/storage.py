from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticStorage(CompressedManifestStaticFilesStorage):
    """Fingerprinted file names so browsers (incl. iPad Safari) pick up updates straight away."""

    # Fall back to plain names when collectstatic hasn't run (tests, development).
    manifest_strict = False
