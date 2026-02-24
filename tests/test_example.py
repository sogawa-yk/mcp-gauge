import pytest

from src.example import add, divide, multiply, subtract


class TestAdd:
    def test_positive_numbers(self):
        # Given: 準備
        a, b = 2, 3

        # When: 実行
        result = add(a, b)

        # Then: 検証
        assert result == 5

    def test_negative_numbers(self):
        # Given: 準備
        a, b = -2, 3

        # When: 実行
        result = add(a, b)

        # Then: 検証
        assert result == 1


class TestSubtract:
    def test_positive_numbers(self):
        # Given: 準備
        a, b = 5, 3

        # When: 実行
        result = subtract(a, b)

        # Then: 検証
        assert result == 2


class TestMultiply:
    def test_positive_numbers(self):
        # Given: 準備
        a, b = 2, 3

        # When: 実行
        result = multiply(a, b)

        # Then: 検証
        assert result == 6

    def test_zero(self):
        # Given: 準備
        a, b = 5, 0

        # When: 実行
        result = multiply(a, b)

        # Then: 検証
        assert result == 0


class TestDivide:
    def test_positive_numbers(self):
        # Given: 準備
        a, b = 6, 3

        # When: 実行
        result = divide(a, b)

        # Then: 検証
        assert result == 2

    def test_division_by_zero(self):
        # Given: 準備
        a, b = 5, 0

        # When/Then: 実行と検証
        with pytest.raises(ValueError, match="Division by zero is not allowed"):
            divide(a, b)
