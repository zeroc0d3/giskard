from typing import Optional, Sequence

import logging
import textwrap

import numpy as np
import pandas as pd
import umap
from bokeh.io import output_notebook, reset_output, show
from bokeh.models import ColumnDataSource, HoverTool, LabelSet
from bokeh.palettes import Category20
from bokeh.plotting import figure
from sklearn.cluster import HDBSCAN

from ..core.errors import GiskardInstallationError
from ..datasets.metadata.text_metadata_provider import _detect_lang
from ..llm.client import LLMClient, LLMMessage, get_default_client

logger = logging.getLogger(__name__)


TOPIC_SUMMARIZATION_PROMPT = """You are a superpowerful summarization AI model. 

Your task is to summarize a list of paragraphs and extract the topic in common to ALL paragraphs.
- Your answer must be 3 to 5 words at most.
- The summary must be written in {language}.

All the information about the topic is delimited with  <topic></topic> tags.
The paragraphs will be separated with "----------".
Here is the list of paragraphs:
<topic>
{topics_elements}
</topic>

Make sure to only return the summary as a valid string, starting and ending with quotes."""


class Document:
    """A class to wrap the elements of the knowledge base into a unified format."""

    def __init__(self, document: dict, idx: int, features: Optional[Sequence] = None):
        features = features if features is not None else list(document.keys())

        if len(features) == 1:
            self.content = document[features[0]]
        else:
            self.content = "\n".join(f"{feat}: {document[feat]}" for feat in features)

        self.metadata = document
        self.id = idx
        self.embeddings = None


class KnowledgeBase:
    """
    A class to handle the knowledge base and the associated vector store.

    Parameters
    ----------
    knowledge_base_df: pd.DataFrame
        A dataframe containing the whole knowledge base.
    knowledge_base_columns: Sequence[str], optional
        The list of columns from the `knowledge_base` to consider. If not specified, all columns of the knowledge base
        dataframe will be concatenated to produce a single document.
        Example: if your knowledge base consists in FAQ data with columns "Q" and "A", we will format each row into a
        single document "Q: [question]\\nA: [answer]" to generate questions.
    context_neighbors: int = 4
        The maximum number of extracted element from the knowledge base to get a relevant context for question generation
    context_similarity_threshold: float = 0.2
        A similarity threshold to filter irrelevant element from the knowledge base during context creation
    seed: int, optional
        The seed to use for random number generation.
    llm_client: LLMClient, optional:
        The LLM client to use for question generation. If not specified, a default openai client will be used.
    embedding_model: str = "text-embedding-ada-002"
        The name of the embedding model to use for the knowledge base. It should match the llm_client available embedding models.
    min_topic_size: int = 2
        The minimum number of document to form a topic inside the knowledge base.
    """

    def __init__(
        self,
        knowledge_base_df: pd.DataFrame,
        knowledge_base_columns: Sequence[str] = None,
        context_neighbors: int = 4,
        context_similarity_threshold: float = 0.2,
        seed: int = None,
        llm_client: Optional[LLMClient] = None,
        embedding_model: Optional[str] = "text-embedding-ada-002",
        min_topic_size: Optional[int] = None,
        chunk_size: int = 2048,
    ) -> None:
        if len(knowledge_base_df) > 0:
            self._documents = [
                Document(
                    knowledge_chunk,
                    features=knowledge_base_columns,
                    idx=idx if "id" not in knowledge_chunk else knowledge_chunk.pop("id"),
                )
                for idx, knowledge_chunk in enumerate(knowledge_base_df.to_dict("records"))
            ]
        else:
            raise ValueError("Cannot generate a vector store from empty DataFrame.")

        self._knowledge_base_df = knowledge_base_df
        self._knowledge_base_columns = knowledge_base_columns
        self._context_similarity_threshold = context_similarity_threshold
        self._context_neighbors = context_neighbors

        self._rng = np.random.default_rng(seed=seed)
        self._llm_client = llm_client or get_default_client()
        self._embedding_model = embedding_model

        self._min_topic_size = min_topic_size or round(2 + np.log(len(self._documents)))
        self.chunk_size = chunk_size

        self._embeddings_inst = None
        self._topics_inst = None
        self._index_inst = None
        self._reduced_embeddings_inst = None

        document_languages = [_detect_lang(doc.content[:300]) for doc in self._rng.choice(self._documents, size=10)]
        languages, occurences = np.unique(
            ["en" if (pd.isna(lang) or lang == "unknown") else lang for lang in document_languages], return_counts=True
        )
        self._language = languages[np.argmax(occurences)]

        self._documents_index = {doc.id: doc for doc in self._documents}

    @property
    def _embeddings(self):
        if self._embeddings_inst is None:
            self._embeddings_inst = self._llm_client.embeddings(
                [doc.content for doc in self._documents], model=self._embedding_model, chunk_size=self.chunk_size
            )
            for doc, emb in zip(self._documents, self._embeddings_inst):
                doc.embeddings = emb
        return self._embeddings_inst

    @property
    def _reduced_embeddings(self):
        if self._reduced_embeddings_inst is None:
            logger.debug("Calculating UMAP projection")
            reducer = umap.UMAP(
                n_neighbors=50,
                min_dist=0.5,
                n_components=2,
            )
            self._reduced_embeddings_inst = reducer.fit_transform(self._embeddings)
        return self._reduced_embeddings_inst

    @property
    def _dimension(self):
        return self._embeddings[0].shape[0]

    def get_savable_data(self):
        return {
            "knowledge_base_columns": self._knowledge_base_columns,
            "context_neighbors": self._context_neighbors,
            "context_similarity_threshold": self._context_similarity_threshold,
            "embedding_model": self._embedding_model,
            "min_topic_size": self._min_topic_size,
            "topics": {int(k): topic for k, topic in self.topics.items()},
            "documents_topics": [int(doc.topic_id) for doc in self._documents],
        }

    @property
    def _index(self):
        if self._index_inst is None:
            try:
                from faiss import IndexFlatL2
            except ImportError as err:
                raise GiskardInstallationError(flavor="llm") from err

            self._index_inst = IndexFlatL2(self._dimension)
            self._index_inst.add(self._embeddings)
        return self._index_inst

    @property
    def topics(self):
        if self._topics_inst is None:
            self._topics_inst = self._find_topics()
        return self._topics_inst

    def _find_topics(self):
        logger.debug("Running HDBSCAN to cluster topics")
        hdbscan = HDBSCAN(
            min_cluster_size=self._min_topic_size,
            min_samples=3,
            metric="euclidean",
            cluster_selection_epsilon=0.0,
        )
        clustering = hdbscan.fit(self._reduced_embeddings)
        for i, doc in enumerate(self._documents):
            doc.topic_id = clustering.labels_[i]

        topics_ids = set(clustering.labels_)
        topics = {
            idx: self._get_topic_name([self._documents[doc_id] for doc_id in np.nonzero(clustering.labels_ == idx)[0]])
            for idx in topics_ids
            if idx != -1
        }
        topics[-1] = "Others"

        return topics

    def _get_topic_name(self, topic_documents):
        logger.debug("Create topic name from topic documents")

        self._rng.shuffle(topic_documents)
        topics_str = "\n\n".join(["----------" + doc.content for doc in topic_documents])

        # prevent context window overflow
        topics_str = topics_str[: 3 * 8192]
        prompt = TOPIC_SUMMARIZATION_PROMPT.format(language=self._language, topics_elements=topics_str)

        return self._llm_client.complete([LLMMessage(role="user", content=prompt)], temperature=0.0).content[1:-1]

    def plot_topics(self, notebook: bool = True):
        if notebook:
            output_notebook()
        else:
            reset_output()
        show(self._get_knowledge_plot())

    def _get_failure_plot(self, question_evaluation: Sequence[dict] = None):
        document_ids = [question["metadata"]["seed_document_id"] for question in question_evaluation]
        reduced_embeddings = self._reduced_embeddings[document_ids]

        TITLE = "Knowledge Base UMAP representation"

        topics = [question["metadata"]["topic"] for question in question_evaluation]
        failure_palette = ["#ba0e0e", "#0a980a"]
        questions = [question["question"] for question in question_evaluation]
        assistant_answer = [question["assistant_answer"] for question in question_evaluation]
        reference_answer = [question["reference_answer"] for question in question_evaluation]
        correctness = [question["correctness"] for question in question_evaluation]
        colors = [failure_palette[question["correctness"]] for question in question_evaluation]

        x_min = self._reduced_embeddings[:, 0].min()
        x_max = self._reduced_embeddings[:, 0].max()
        y_min = self._reduced_embeddings[:, 1].min()
        y_max = self._reduced_embeddings[:, 1].max()

        x_range = (x_min - (x_max - x_min) * 0.05, x_max + (x_max - x_min) * 0.6)
        y_range = (y_min - (y_max - y_min) * 0.25, y_max + (y_max - y_min) * 0.25)

        source = ColumnDataSource(
            data={
                "x": reduced_embeddings[:, 0],
                "y": reduced_embeddings[:, 1],
                "topic": [textwrap.fill(t) for t in topics],
                "correctness": correctness,
                "questions": questions,
                "assistant_answer": assistant_answer,
                "reference_answer": reference_answer,
                "id": document_ids,
                "content": [self._documents[doc_id].content[:500] for doc_id in document_ids],
                "color": colors,
            }
        )

        hover = HoverTool(
            mode="mouse",
            tooltips="""
        <div style="width:400px;">
        <b>Document id:</b> @id <br>
        <b>Topic:</b> @topic <br>
        <b>Question:</b> @questions <br>
        <b>Assistant Answer:</b> @assistant_answer <br>
        <b>Reference Answer:</b> @reference_answer <br>
        <b>Correctness:</b> @correctness <br>
        <b>Content:</b> @content
        </div>
        """,
        )

        p = figure(
            tools=["pan", "wheel_zoom", "box_zoom", "reset", "save"],
            toolbar_location="right",
            title=TITLE,
            x_range=x_range,
            y_range=y_range,
            sizing_mode="stretch_width",
        )
        p.add_tools(hover)
        p.toolbar.logo = "grey"
        p.background_fill_color = "#efefef"
        p.grid.grid_line_color = "white"

        foreground_scatter = p.scatter(
            x="x",
            y="y",
            source=source,
            color="color",
            line_color="color",
            line_alpha=1.0,
            line_width=2,
            alpha=0.7,
            size=12,
            legend_group="correctness",
        )

        hover.renderers = [foreground_scatter]

        p.legend.location = "top_right"
        p.legend.title = "Knowledge Base Correctness"
        p.legend.title_text_font_style = "bold"
        p.title.text_font_size = "14pt"

        background_source = ColumnDataSource(
            data={
                "x": self._reduced_embeddings[:, 0],
                "y": self._reduced_embeddings[:, 1],
            }
        )

        p.scatter(
            x="x",
            y="y",
            source=background_source,
            color="grey",
            alpha=0.2,
            size=12,
        )
        if len(self.topics) > 1:
            topic_centers = np.array(
                [
                    np.mean(
                        [self._reduced_embeddings[doc.id] for doc in self._documents if doc.topic_id == topic_id],
                        axis=0,
                    )
                    for topic_id in range(len(self.topics) - 1)
                ]
            )
            topics = [self.topics[topic_id] for topic_id in range(len(self.topics) - 1)]
            label_source = ColumnDataSource(
                data={
                    "x": topic_centers[:, 0],
                    "y": topic_centers[:, 1],
                    "topic": topics,
                }
            )

            labels = LabelSet(
                x="x",
                y="y",
                text="topic",
                level="glyph",
                text_align="center",
                text_font_size="12pt",
                text_font_style="bold",
                source=label_source,
            )
            p.add_layout(labels)

        return p

    def _get_knowledge_plot(self):
        if self.topics is None:
            raise ValueError("No topics found.")

        TITLE = "Knowledge Base UMAP representation"
        TOOLS = "hover,pan,wheel_zoom,box_zoom,reset,save"

        topics_ids = [doc.topic_id for doc in self._documents]
        palette = Category20[20]

        colors = np.array([palette[topic % 20] if topic >= 0 else "#999" for topic in topics_ids])

        x_min = self._reduced_embeddings[:, 0].min()
        x_max = self._reduced_embeddings[:, 0].max()
        y_min = self._reduced_embeddings[:, 1].min()
        y_max = self._reduced_embeddings[:, 1].max()

        x_range = (x_min - (x_max - x_min) * 0.05, x_max + (x_max - x_min) * 0.6)
        y_range = (y_min - (y_max - y_min) * 0.25, y_max + (y_max - y_min) * 0.25)

        source = ColumnDataSource(
            data={
                "x": self._reduced_embeddings[:, 0],
                "y": self._reduced_embeddings[:, 1],
                "topic": [textwrap.fill(self.topics[topic_id], 40) for topic_id in topics_ids],
                "id": [doc.id for doc in self._documents],
                "content": [doc.content[:500] for doc in self._documents],
                "color": colors,
            }
        )
        p = figure(
            tools=TOOLS,
            toolbar_location="right",
            title=TITLE,
            x_range=x_range,
            y_range=y_range,
            sizing_mode="stretch_width",
        )
        p.toolbar.logo = "grey"
        p.background_fill_color = "#efefef"
        p.grid.grid_line_color = "white"

        p.hover.tooltips = """
        <div style="width:400px;">
        <b>Document id:</b> @id <br>
        <b>Topic:</b> @topic <br>
        <b>Document Content:</b> @content
        </div>
        """

        p.scatter(
            x="x",
            y="y",
            source=source,
            color="color",
            line_color="color",
            line_alpha=1.0,
            line_width=2,
            alpha=0.7,
            size=5,
            legend_group="topic",
        )
        p.legend.location = "top_right"
        p.legend.title = "Knowledge Base Topics"
        p.legend.title_text_font_style = "bold"
        p.title.text_font_size = "14pt"

        return p

    def _get_random_document(self):
        return self._rng.choice(self._documents)

    def _get_random_document_group(self):
        seed_document_idx = self._rng.choice(len(self._embeddings))
        seed_embedding = self._embeddings[seed_document_idx]
        topic = self._documents[seed_document_idx].topic_id

        relevant_documents = [
            document
            for (document, score) in self.vector_similarity_search_with_score(seed_embedding, k=self._context_neighbors)
            if score < self._context_similarity_threshold
        ]

        return relevant_documents, topic

    def similarity_search_with_score(self, query: Sequence[str], k: int) -> Sequence:
        query_emb = self._llm_client.embeddings(query, model=self._embedding_model).astype("float32")
        return self.vector_similarity_search_with_score(query_emb, k)

    def vector_similarity_search_with_score(self, query_emb: np.ndarray, k: int) -> Sequence:
        query_emb = np.atleast_2d(query_emb)
        distances, indices = self._index.search(query_emb, k)
        return [(self._documents[i], d) for d, i in zip(distances[0], indices[0])]