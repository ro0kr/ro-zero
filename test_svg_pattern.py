import tempfile
import unittest
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont

from build_font import build_ro_zero_font
from svg_pattern import PatternConfig, build_fracture, char_seed
from type_shatter import black900_radius, render_line, shatter_glyph, shatter_glyph_em


class SeedTests(unittest.TestCase):
    def test_ascii_code_is_the_seed(self) -> None:
        self.assertEqual(char_seed("A"), 65)
        self.assertEqual(char_seed("B"), 66)
        self.assertEqual(char_seed(" "), 32)

    def test_non_ascii_uses_code_point(self) -> None:
        self.assertEqual(char_seed("한"), ord("한"))
        self.assertEqual(char_seed("Я"), ord("Я"))

    def test_weight_does_not_change_seed(self) -> None:
        a900, _ = shatter_glyph("A", 900)
        a100, _ = shatter_glyph("A", 100)
        self.assertGreater(len(a900), 0)
        # Same character, same mesh seed. Thin just keeps fewer rounded shards.
        self.assertGreaterEqual(len(a900), len(a100))


class ShatterTests(unittest.TestCase):
    def test_gap_ratio_near_thirty(self) -> None:
        result = build_fracture(PatternConfig(seed=65))
        self.assertGreaterEqual(result.piece_count, 40)
        self.assertGreater(result.white_ratio, 0.12)
        self.assertLess(result.white_ratio, 0.5)

    def test_radius_comes_from_black_900(self) -> None:
        self.assertGreater(black900_radius(120), 0.5)

    def test_svg_has_black_and_no_white_fill(self) -> None:
        paths, _ = render_line("A", 500, 0, 0, 80)
        self.assertGreater(len(paths), 0)
        joined = "".join(paths)
        self.assertNotIn("#ffffff", joined)
        self.assertNotIn("white", joined.lower())

    def test_em_shatter_keeps_font_units(self) -> None:
        pieces, advance = shatter_glyph_em("A", 500)
        self.assertGreater(len(pieces), 0)
        self.assertGreater(advance, 100)
        minx, miny, maxx, maxy = pieces[0].bounds
        self.assertLess(maxx, 1200)
        self.assertGreater(maxy, -200)

    def test_thin_marks_keep_unfilleted_shards(self) -> None:
        pieces, advance = shatter_glyph_em("_", 500)
        self.assertGreater(advance, 0)
        self.assertGreater(len(pieces), 0)

    def test_ro_zero_font_file(self) -> None:
        codes = [ord(ch) for ch in "가나다라abcd1234"]
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "ro-zero.ttf"
            build_ro_zero_font(dest=dest, codes=codes, workers=1, install=False)
            raw = dest.read_bytes()
            self.assertEqual(raw[:4], b"\x00\x01\x00\x00")
            font = TTFont(dest)
            cmap = font.getBestCmap()
            self.assertIn(ord("a"), cmap)
            self.assertIn(ord("가"), cmap)
            self.assertGreater(font["glyf"][cmap[ord("가")]].numberOfContours, 0)

    def test_family_zip_contains_nine_ttfs(self) -> None:
        from build_font import FAMILY_WEIGHTS, build_family_zip

        codes = [ord(ch) for ch in "가A"]
        with tempfile.TemporaryDirectory() as tmp:
            archive = build_family_zip(codes=codes, workers=1, out_dir=Path(tmp), report=False)
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
            self.assertIn("OFL.txt", names)
            for _weight, style in FAMILY_WEIGHTS:
                self.assertIn(f"RoZero-{style}.ttf", names)
            thin = Path(tmp) / "family" / "RoZero-Thin.ttf"
            black = Path(tmp) / "family" / "RoZero-Black.ttf"
            self.assertEqual(thin.read_bytes()[:4], b"\x00\x01\x00\x00")
            self.assertEqual(TTFont(thin)["OS/2"].usWeightClass, 100)
            self.assertEqual(TTFont(black)["OS/2"].usWeightClass, 900)


class ForkDocsTests(unittest.TestCase):
    def test_ofl_says_noto_sans_fork(self) -> None:
        text = (Path(__file__).resolve().parent / "OFL.txt").read_text(encoding="utf-8")
        self.assertIn("fork of Noto Sans", text)
        self.assertIn("Ro Zero", text)
        self.assertNotIn('Reserved Font Name "Noto"', text)

    def test_readme_and_description_name_the_fork(self) -> None:
        root = Path(__file__).resolve().parent
        readme = (root / "README.md").read_text(encoding="utf-8")
        desc = (root / "documentation" / "DESCRIPTION.en_us.html").read_text(encoding="utf-8")
        self.assertIn("fork of", readme)
        self.assertIn("Noto Sans", readme)
        self.assertIn("fork of Noto Sans", desc)

    def test_noto_sources_live_under_fonts_noto(self) -> None:
        from type_shatter import FONTS

        self.assertEqual(FONTS.name, "noto")
        self.assertTrue((FONTS / "NotoSans-Variable.ttf").exists())


if __name__ == "__main__":
    unittest.main()
