import logging
import posixpath
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Dict, Optional, List

import pandas as pd
import yaml
from zstandard import ZstdDecompressor

from giskard.client.giskard_client import GiskardClient
from giskard.client.io_utils import save_df, compress
from giskard.core.core import DatasetMeta, SupportedFeatureTypes
from giskard.settings import settings

logger = logging.getLogger(__name__)


class Dataset:
    name: str
    target: str
    feature_types: Dict[str, str]
    df: pd.DataFrame
    id: uuid.UUID

    def __init__(
            self,
            df: pd.DataFrame,
            name: Optional[str] = None,
            target: Optional[str] = None,
            cat_columns: Optional[List[str]] = None,
            feature_types: Optional[Dict[str, str]] = None,
            id: Optional[uuid.UUID] = None
    ) -> None:
        self.name = name
        self.df = pd.DataFrame(df)
        self.target = target
        self.column_types = self.extract_column_types(self.df)
        self.feature_types = feature_types if feature_types else self.extract_feature_types(
            list(self.column_types.keys()), cat_columns)

    @staticmethod
    def extract_feature_types(all_columns, cat_columns):
        feature_types = {}
        if cat_columns:
            for cat_col in cat_columns:
                feature_types[cat_col] = SupportedFeatureTypes.CATEGORY.value
            for col in all_columns:
                if col not in cat_columns:
                    feature_types[col] = SupportedFeatureTypes.NUMERIC.value if type(col) != str else SupportedFeatureTypes.TEXT.value
        else:  # TODO: Implement smarter inference
            for col in all_columns:
                feature_types[col] = SupportedFeatureTypes.NUMERIC.value if type(col) != str else SupportedFeatureTypes.TEXT.value

        return feature_types
        if id is None:
            self.id = uuid.uuid4()
        else:
            self.id = id

    @staticmethod
    def extract_column_types(df):
        return df.dtypes.apply(lambda x: x.name).to_dict()

    def upload(self, client: GiskardClient, project_key: str):
        from giskard.core.dataset_validation import validate_dataset

        validate_dataset(self)

        dataset_id = str(self.id)

        with tempfile.TemporaryDirectory(prefix="giskard-dataset-") as local_path:
            original_size_bytes, compressed_size_bytes = self.save(Path(local_path), dataset_id)
            if client is not None:
                client.log_artifacts(local_path, posixpath.join(project_key, "datasets", dataset_id))
            client.save_dataset_meta(
                project_key,
                dataset_id,
                self.meta,
                original_size_bytes=original_size_bytes,
                compressed_size_bytes=compressed_size_bytes,
            )
        return dataset_id

    @property
    def meta(self):
        return DatasetMeta(
            name=self.name, target=self.target, feature_types=self.feature_types, column_types=self.column_types
        )

    @staticmethod
    def cast_column_to_types(df, column_types):
        current_types = df.dtypes.apply(lambda x: x.name).to_dict()
        logger.info(f"Casting dataframe columns from {current_types} to {column_types}")
        if column_types:
            try:
                df = df.astype(column_types)
            except Exception as e:
                raise ValueError("Failed to apply column types to dataset") from e
        return df

    @classmethod
    def load(cls, local_path: str):
        with open(local_path, "rb") as ds_stream:
            return pd.read_csv(
                ZstdDecompressor().stream_reader(ds_stream),
                keep_default_na=False,
                na_values=["_GSK_NA_"],
            )

    @classmethod
    def download(cls, client: GiskardClient, project_key, dataset_id):
        local_dir = settings.home_dir / settings.cache_dir / project_key / "datasets" / dataset_id

        if client is None:
            # internal worker case, no token based http client
            assert local_dir.exists(), f"Cannot find existing dataset {project_key}.{dataset_id}"
            with open(Path(local_dir) / "giskard-dataset-meta.yaml") as f:
                saved_meta = yaml.load(f, Loader=yaml.Loader)
                meta = DatasetMeta(
                    name=saved_meta["name"],
                    target=saved_meta["target"],
                    feature_types=saved_meta["feature_types"],
                    column_types=saved_meta["column_types"],
                )
        else:
            client.load_artifact(local_dir, posixpath.join(project_key, "datasets", dataset_id))
            meta: DatasetMeta = client.load_dataset_meta(project_key, dataset_id)

        df = cls.load(local_dir / "data.csv.zst")
        df = cls.cast_column_to_types(df, meta.column_types)
        return cls(df=df, name=meta.name, target=meta.target, feature_types=meta.feature_types,
                   id=uuid.UUID(dataset_id)
                   )

    @staticmethod
    def _cat_columns(meta):
        return [fname for (fname, ftype) in meta.feature_types.items() if
                ftype == SupportedFeatureTypes.CATEGORY] if meta.feature_types else None

    @property
    def cat_columns(self):
        return self._cat_columns(self.meta)

    def save(self, local_path: Path, dataset_id):
        with open(local_path / "data.csv.zst", "wb") as f:
            uncompressed_bytes = save_df(self.df)
            compressed_bytes = compress(uncompressed_bytes)
            f.write(compressed_bytes)
            original_size_bytes, compressed_size_bytes = len(uncompressed_bytes), len(compressed_bytes)

            with open(Path(local_path) / "giskard-dataset-meta.yaml", "w") as meta_f:
                yaml.dump(
                    {
                        "id": dataset_id,
                        "name": self.meta.name,
                        "target": self.meta.target,
                        "feature_types": self.meta.feature_types,
                        "column_types": self.meta.column_types,
                        "original_size_bytes": original_size_bytes,
                        "compressed_size_bytes": compressed_size_bytes,
                    },
                    meta_f,
                    default_flow_style=False,
                )
            return original_size_bytes, compressed_size_bytes

    @property
    def columns(self):
        return self.df.columns

    def slice(self, slice_fn: Callable):
        if slice_fn is None:
            return self
        return Dataset(df=slice_fn(self.df), name=self.name, target=self.target, feature_types=self.feature_types)

    def __len__(self):
        return len(self.df)
