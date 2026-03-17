from cortex.embeddings import Embedder, serialize_f32


class TestSerializeF32:
    def test_byte_length_matches_vector_dims(self):
        vec = [0.1, 0.2, 0.3]
        result = serialize_f32(vec)
        assert len(result) == 3 * 4  # 3 floats * 4 bytes each

    def test_768_dim_vector(self):
        vec = [0.0] * 768
        result = serialize_f32(vec)
        assert len(result) == 768 * 4

    def test_empty_vector(self):
        result = serialize_f32([])
        assert len(result) == 0


class TestEmbedder:
    def test_singleton_returns_same_instance(self):
        a = Embedder.get()
        b = Embedder.get()
        assert a is b

    def test_encode_returns_768_floats(self):
        result = Embedder.get().encode("hello world")
        assert len(result) == 768
        assert all(isinstance(x, float) for x in result)

    def test_encode_batch_matches_individual(self):
        texts = ["hello", "world"]
        batch = Embedder.get().encode_batch(texts)
        individual = [Embedder.get().encode(t) for t in texts]
        assert len(batch) == 2
        for b, i in zip(batch, individual):
            assert b == i

    def test_same_text_produces_same_embedding(self):
        a = Embedder.get().encode("test input")
        b = Embedder.get().encode("test input")
        assert a == b

    def test_different_text_produces_different_embedding(self):
        a = Embedder.get().encode("hello")
        b = Embedder.get().encode("goodbye")
        assert a != b
