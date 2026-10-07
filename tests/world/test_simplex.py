import unittest

from modules.world.simplex import PERM, noise


class SimplexPortTest(unittest.TestCase):
    """weather: What we port: the noise matches the reference algorithm."""

    def test_permutation_table_is_a_doubled_permutation(self):
        self.assertEqual(len(PERM), 512)
        self.assertEqual(sorted(PERM[:256]), list(range(256)))
        self.assertEqual(PERM[:256], PERM[256:])

    def test_origin_is_zero(self):
        self.assertEqual(noise(0, 0), 0.0)

    def test_hand_computed_point(self):
        # Corners (0,0), (1,0), (1,1) with gradients (-1,0), (1,-1), (0,1):
        # 70 * (0.0039063*-0.5 + 0.019152*-0.5 + 0.000667*-0.57735) = -0.83398
        self.assertAlmostEqual(noise(0.5, 0.0), -0.83398, places=4)

    def test_reference_values_cover_both_triangles_and_wrapped_cells(self):
        # Computed with an independent implementation of the classic algorithm.
        reference = [
            (0.2, 0.7, 0.1857186624215856),
            (0.7, 0.2, -0.7444791479834648),
            (-3.2, 5.9, 0.5220447884768876),
            (200.3, 150.7, -0.40106159194279445),
            (130.6, 129.1, -0.40609415834547824),
            (-140.4, -200.8, -0.3798336914731493),
            (3.3, -0.4, -0.1092986360878231),
        ]
        for x, y, expected in reference:
            self.assertAlmostEqual(noise(x, y), expected, places=9)

    def test_output_is_bounded_and_deterministic(self):
        for i in range(400):
            value = noise(i * 0.37, i * 0.11 + 5)
            self.assertLessEqual(abs(value), 1.0)
            self.assertEqual(value, noise(i * 0.37, i * 0.11 + 5))


if __name__ == "__main__":
    unittest.main()
