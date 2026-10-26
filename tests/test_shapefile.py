"""
This module tests the functionality of shapefile.py.
"""

import contextlib
import datetime
import io
import json
import os.path
from pathlib import Path
import shutil
import struct
import zipfile

# third party imports
import pytest

# our imports (the code under test)
import shapefile

# helper functions
from .run_doctests import (
    REPLACE_REMOTE_URLS_WITH_LOCALHOST,
    _replace_remote_url_with_localhost,
)

shapefiles_dir = Path(__file__).parent / "shapefiles"

# define various test shape tuples of (type, points, parts indexes, and expected geo interface output)
geo_interface_tests = [
    (
        shapefile.POINT,  # point
        [(1, 1)],
        [],
        {"type": "Point", "coordinates": (1, 1)},
    ),
    (
        shapefile.MULTIPOINT,  # multipoint
        [(1, 1), (2, 1), (2, 2)],
        [],
        {"type": "MultiPoint", "coordinates": [(1, 1), (2, 1), (2, 2)]},
    ),
    (
        shapefile.POLYLINE,  # single linestring
        [(1, 1), (2, 1)],
        [0],
        {"type": "LineString", "coordinates": [(1, 1), (2, 1)]},
    ),
    (
        shapefile.POLYLINE,  # multi linestring
        [
            (1, 1),
            (2, 1),  # line 1
            (10, 10),
            (20, 10),
        ],  # line 2
        [0, 2],
        {
            "type": "MultiLineString",
            "coordinates": [
                [(1, 1), (2, 1)],  # line 1
                [(10, 10), (20, 10)],  # line 2
            ],
        },
    ),
    (
        shapefile.POLYGON,  # single polygon, no holes
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior
        ],
        [0],
        {
            "type": "Polygon",
            "coordinates": [
                [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],
            ],
        },
    ),
    (
        shapefile.POLYGON,  # single polygon, holes (ordered)
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior
            (2, 2),
            (4, 2),
            (4, 4),
            (2, 4),
            (2, 2),  # hole 1
            (5, 5),
            (7, 5),
            (7, 7),
            (5, 7),
            (5, 5),  # hole 2
        ],
        [0, 5, 5 + 5],
        {
            "type": "Polygon",
            "coordinates": [
                [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],  # exterior
                [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)],  # hole 1
                [(5, 5), (7, 5), (7, 7), (5, 7), (5, 5)],  # hole 2
            ],
        },
    ),
    (
        shapefile.POLYGON,  # single polygon, holes (unordered)
        [
            (2, 2),
            (4, 2),
            (4, 4),
            (2, 4),
            (2, 2),  # hole 1
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior
            (5, 5),
            (7, 5),
            (7, 7),
            (5, 7),
            (5, 5),  # hole 2
        ],
        [0, 5, 5 + 5],
        {
            "type": "Polygon",
            "coordinates": [
                [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],  # exterior
                [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)],  # hole 1
                [(5, 5), (7, 5), (7, 7), (5, 7), (5, 5)],  # hole 2
            ],
        },
    ),
    (
        shapefile.POLYGON,  # multi polygon, no holes
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior
            (11, 11),
            (11, 19),
            (19, 19),
            (19, 11),
            (11, 11),  # exterior
        ],
        [0, 5],
        {
            "type": "MultiPolygon",
            "coordinates": [
                [  # poly 1
                    [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],
                ],
                [  # poly 2
                    [(11, 11), (11, 19), (19, 19), (19, 11), (11, 11)],
                ],
            ],
        },
    ),
    (
        shapefile.POLYGON,  # multi polygon, holes (unordered)
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior 1
            (11, 11),
            (11, 19),
            (19, 19),
            (19, 11),
            (11, 11),  # exterior 2
            (12, 12),
            (14, 12),
            (14, 14),
            (12, 14),
            (12, 12),  # hole 2.1
            (15, 15),
            (17, 15),
            (17, 17),
            (15, 17),
            (15, 15),  # hole 2.2
            (2, 2),
            (4, 2),
            (4, 4),
            (2, 4),
            (2, 2),  # hole 1.1
            (5, 5),
            (7, 5),
            (7, 7),
            (5, 7),
            (5, 5),  # hole 1.2
        ],
        [0, 5, 10, 15, 20, 25],
        {
            "type": "MultiPolygon",
            "coordinates": [
                [  # poly 1
                    [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],  # exterior
                    [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)],  # hole 1
                    [(5, 5), (7, 5), (7, 7), (5, 7), (5, 5)],  # hole 2
                ],
                [  # poly 2
                    [(11, 11), (11, 19), (19, 19), (19, 11), (11, 11)],  # exterior
                    [(12, 12), (14, 12), (14, 14), (12, 14), (12, 12)],  # hole 1
                    [(15, 15), (17, 15), (17, 17), (15, 17), (15, 15)],  # hole 2
                ],
            ],
        },
    ),
    (
        shapefile.POLYGON,  # multi polygon, nested exteriors with holes (unordered)
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior 1
            (3, 3),
            (3, 7),
            (7, 7),
            (7, 3),
            (3, 3),  # exterior 2
            (4.5, 4.5),
            (4.5, 5.5),
            (5.5, 5.5),
            (5.5, 4.5),
            (4.5, 4.5),  # exterior 3
            (4, 4),
            (6, 4),
            (6, 6),
            (4, 6),
            (4, 4),  # hole 2.1
            (2, 2),
            (8, 2),
            (8, 8),
            (2, 8),
            (2, 2),  # hole 1.1
        ],
        [0, 5, 10, 15, 20],
        {
            "type": "MultiPolygon",
            "coordinates": [
                [  # poly 1
                    [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],  # exterior 1
                    [(2, 2), (8, 2), (8, 8), (2, 8), (2, 2)],  # hole 1.1
                ],
                [  # poly 2
                    [(3, 3), (3, 7), (7, 7), (7, 3), (3, 3)],  # exterior 2
                    [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)],  # hole 2.1
                ],
                [  # poly 3
                    [
                        (4.5, 4.5),
                        (4.5, 5.5),
                        (5.5, 5.5),
                        (5.5, 4.5),
                        (4.5, 4.5),
                    ],  # exterior 3
                ],
            ],
        },
    ),
    (
        shapefile.POLYGON,  # multi polygon, nested exteriors with holes (unordered and tricky holes designed to throw off ring_sample() test)
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior 1
            (3, 3),
            (3, 7),
            (7, 7),
            (7, 3),
            (3, 3),  # exterior 2
            (4.5, 4.5),
            (4.5, 5.5),
            (5.5, 5.5),
            (5.5, 4.5),
            (4.5, 4.5),  # exterior 3
            (4, 4),
            (4, 4),
            (6, 4),
            (6, 4),
            (6, 4),
            (6, 6),
            (4, 6),
            (4, 4),  # hole 2.1 (hole has duplicate coords)
            (2, 2),
            (3, 3),
            (4, 2),
            (8, 2),
            (8, 8),
            (4, 8),
            (2, 8),
            (2, 4),
            (
                2,
                2,
            ),  # hole 1.1 (hole coords form straight line and starts in concave orientation)
        ],
        [0, 5, 10, 15, 20 + 3],
        {
            "type": "MultiPolygon",
            "coordinates": [
                [  # poly 1
                    [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],  # exterior 1
                    [
                        (2, 2),
                        (3, 3),
                        (4, 2),
                        (8, 2),
                        (8, 8),
                        (4, 8),
                        (2, 8),
                        (2, 4),
                        (2, 2),
                    ],  # hole 1.1
                ],
                [  # poly 2
                    [(3, 3), (3, 7), (7, 7), (7, 3), (3, 3)],  # exterior 2
                    [
                        (4, 4),
                        (4, 4),
                        (6, 4),
                        (6, 4),
                        (6, 4),
                        (6, 6),
                        (4, 6),
                        (4, 4),
                    ],  # hole 2.1
                ],
                [  # poly 3
                    [
                        (4.5, 4.5),
                        (4.5, 5.5),
                        (5.5, 5.5),
                        (5.5, 4.5),
                        (4.5, 4.5),
                    ],  # exterior 3
                ],
            ],
        },
    ),
    (
        shapefile.POLYGON,  # multi polygon, holes incl orphaned holes (unordered), should raise warning
        [
            (1, 1),
            (1, 9),
            (9, 9),
            (9, 1),
            (1, 1),  # exterior 1
            (11, 11),
            (11, 19),
            (19, 19),
            (19, 11),
            (11, 11),  # exterior 2
            (12, 12),
            (14, 12),
            (14, 14),
            (12, 14),
            (12, 12),  # hole 2.1
            (15, 15),
            (17, 15),
            (17, 17),
            (15, 17),
            (15, 15),  # hole 2.2
            (95, 95),
            (97, 95),
            (97, 97),
            (95, 97),
            (95, 95),  # hole x.1 (orphaned hole, should be interpreted as exterior)
            (2, 2),
            (4, 2),
            (4, 4),
            (2, 4),
            (2, 2),  # hole 1.1
            (5, 5),
            (7, 5),
            (7, 7),
            (5, 7),
            (5, 5),  # hole 1.2
        ],
        [0, 5, 10, 15, 20, 25, 30],
        {
            "type": "MultiPolygon",
            "coordinates": [
                [  # poly 1
                    [(1, 1), (1, 9), (9, 9), (9, 1), (1, 1)],  # exterior
                    [(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)],  # hole 1
                    [(5, 5), (7, 5), (7, 7), (5, 7), (5, 5)],  # hole 2
                ],
                [  # poly 2
                    [(11, 11), (11, 19), (19, 19), (19, 11), (11, 11)],  # exterior
                    [(12, 12), (14, 12), (14, 14), (12, 14), (12, 12)],  # hole 1
                    [(15, 15), (17, 15), (17, 17), (15, 17), (15, 15)],  # hole 2
                ],
                [  # poly 3 (orphaned hole)
                    [(95, 95), (97, 95), (97, 97), (95, 97), (95, 95)],  # exterior
                ],
            ],
        },
    ),
    (
        shapefile.POLYGON,  # multi polygon, exteriors with wrong orientation (be nice and interpret as such), should raise warning
        [
            (1, 1),
            (9, 1),
            (9, 9),
            (1, 9),
            (1, 1),  # exterior with hole-orientation
            (11, 11),
            (19, 11),
            (19, 19),
            (11, 19),
            (11, 11),  # exterior with hole-orientation
        ],
        [0, 5],
        {
            "type": "MultiPolygon",
            "coordinates": [
                [  # poly 1
                    [(1, 1), (9, 1), (9, 9), (1, 9), (1, 1)],
                ],
                [  # poly 2
                    [(11, 11), (19, 11), (19, 19), (11, 19), (11, 11)],
                ],
            ],
        },
    ),
]


def test_empty_shape_geo_interface():
    """
    Assert that calling __geo_interface__
    on a Shape with no points or parts
    raises an Exception.
    """
    shape = shapefile.Shape()
    with pytest.raises(Exception):
        getattr(shape, "__geo_interface__")


@pytest.mark.parametrize("typ,points,parts,expected", geo_interface_tests)
def test_expected_shape_geo_interface(typ, points, parts, expected):
    """
    Assert that calling __geo_interface__
    on arbitrary input Shape works as expected.
    """
    shape = shapefile.Shape(typ, points, parts)
    geoj = shape.__geo_interface__
    assert geoj == expected


def test_reader_geo_interface():
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as r:
        geoj = r.__geo_interface__
        assert geoj["type"] == "FeatureCollection"
        assert "bbox" in geoj
        assert json.dumps(geoj)


def test_shapes_geo_interface():
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as r:
        geoj = r.shapes().__geo_interface__
        assert geoj["type"] == "GeometryCollection"
        assert json.dumps(geoj)


def test_shaperecords_geo_interface():
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as r:
        geoj = r.shapeRecords().__geo_interface__
        assert geoj["type"] == "FeatureCollection"
        assert json.dumps(geoj)


def test_shaperecord_geo_interface():
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as r:
        for shaperec in r:
            assert json.dumps(shaperec.__geo_interface__)


@pytest.mark.skipif(
    not REPLACE_REMOTE_URLS_WITH_LOCALHOST,
    reason="Flakey test, fails due to Github rate limit",
)
@pytest.mark.network
def test_reader_nvkelso_files_from_localhost_url():
    """
    Assert that Reader can open shapefiles from a url.
    """

    # Only test these shapefiles from localhost,
    # https://github.com/nvkelso/natural-earth-vector urls throws 426 errors ("too many downloads").
    # A suitable repo of test files, and a localhost server setup is
    # defined in ./.github/actions/test/actions.yml

    def Reader(url):
        new_url = _replace_remote_url_with_localhost(url)
        print(f"repr(new_url): {repr(new_url)}")
        return shapefile.Reader(new_url)

    # test with extension
    url = "https://github.com/nvkelso/natural-earth-vector/blob/master/110m_cultural/ne_110m_admin_0_tiny_countries.shp?raw=true"
    with Reader(url) as sf:
        for __recShape in sf.iterShapeRecords():
            pass
    assert sf.shp.closed
    assert sf._shx is None or sf.shx.closed
    assert sf.dbf.closed

    # test without extension
    url = "https://github.com/nvkelso/natural-earth-vector/blob/master/110m_cultural/ne_110m_admin_0_tiny_countries?raw=true"
    with Reader(url) as sf:
        for __recShape in sf.iterShapeRecords():
            pass
        assert len(sf) > 0
    assert sf.shp.closed
    assert sf._shx is None or sf.shx.closed
    assert sf.dbf.closed


@pytest.mark.network
def test_reader_urls():
    """
    Assert that Reader can open shapefiles from a few different urls.
    """

    # Allow testing loading of shapefiles from a url on localhost (to avoid
    # overloading external servers, and associated spurious test failures).
    # A suitable repo of test files, and a localhost server setup is
    # defined in ./.github/actions/test/actions.yml
    if REPLACE_REMOTE_URLS_WITH_LOCALHOST:

        def Reader(url):
            new_url = _replace_remote_url_with_localhost(url)
            print(f"repr(new_url): {repr(new_url)}")
            return shapefile.Reader(new_url)
    else:
        print("Using plain Reader")
        Reader = shapefile.Reader

    # test no files found
    url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/README.md"
    with pytest.raises(shapefile.ShapefileException):
        with Reader(url) as sf:
            pass

    # test reading zipfile from url
    urls = [
        "https://github.com/JamesParrott/PyShp_test_shapefile/raw/main/gis_osm_natural_a_free_1.zip",
        "http://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/ne_10m_admin_0_boundary_lines_land.zip",
    ]
    for url in urls:
        try:
            with Reader(url) as sf:
                for __recShape in sf.iterShapeRecords():
                    pass
                assert len(sf) > 0
        except shapefile.HTTPError:
            pass
        else:
            assert sf.shp.closed is sf.shx.closed is sf.dbf.closed is True
            break
    else:
        raise shapefile.HTTPError(
            "\n".join(urls),
            "Could not download .zipped shapefiles from any of the test urls",
            404,
            {},
            None,
        )


def test_reader_zip():
    """
    Assert that Reader can open shapefiles inside a zipfile.
    """
    # test reading zipfile only
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups.zip") as sf:
        for __recShape in sf.iterShapeRecords():
            pass
        assert len(sf) > 0
    assert sf.shp.closed is sf.shx.closed is sf.dbf.closed is True

    # test require specific path when reading multi-shapefile zipfile
    with pytest.raises(shapefile.ShapefileException):
        with shapefile.Reader(
            f"{shapefiles_dir.as_posix()}/blockgroups_multishapefile.zip"
        ) as sf:
            pass

    # test specifying the path when reading multi-shapefile zipfile (with extension)
    with shapefile.Reader(
        f"{shapefiles_dir.as_posix()}/blockgroups_multishapefile.zip/blockgroups2.shp"
    ) as sf:
        for __recShape in sf.iterShapeRecords():
            pass
        assert len(sf) > 0
    assert sf.shp.closed is sf.shx.closed is sf.dbf.closed is True

    # test specifying the path when reading multi-shapefile zipfile (without extension)
    with shapefile.Reader(
        f"{shapefiles_dir.as_posix()}/blockgroups_multishapefile.zip/blockgroups2"
    ) as sf:
        for __recShape in sf.iterShapeRecords():
            pass
        assert len(sf) > 0
    assert sf.shp.closed is sf.shx.closed is sf.dbf.closed is True

    # test raising error when can't find shapefile inside zipfile
    with pytest.raises(shapefile.ShapefileException):
        with shapefile.Reader(f"{shapefiles_dir.as_posix()}/empty_zipfile.zip") as sf:
            pass


def test_reader_close_path():
    """
    Assert that manually calling Reader.close()
    closes the shp, shx, and dbf files
    on exit, if given paths.
    """
    # note uses an actual shapefile from
    # the projects "shapefiles" directory
    sf = shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups.shp")
    sf.close()

    assert sf.shp.closed is True
    assert sf.dbf.closed is True
    assert sf.shx.closed is True

    # check that can read again
    sf = shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups.shp")
    sf.close()


def test_reader_close_filelike():
    """
    Assert that manually calling Reader.close()
    leaves the shp, shx, and dbf files open
    on exit, if given filelike objects.
    """
    # note uses an actual shapefile from
    # the projects "shapefiles" directory
    shp = open(f"{shapefiles_dir.as_posix()}/blockgroups.shp", mode="rb")
    shx = open(f"{shapefiles_dir.as_posix()}/blockgroups.shx", mode="rb")
    dbf = open(f"{shapefiles_dir.as_posix()}/blockgroups.dbf", mode="rb")
    sf = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
    sf.close()

    assert sf.shp.closed is False
    assert sf.dbf.closed is False
    assert sf.shx.closed is False

    # check that can read again
    sf = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
    sf.close()


def test_reader_context_path():
    """
    Assert that using the context manager
    closes the shp, shx, and dbf files
    on exit, if given paths.
    """
    # note uses an actual shapefile from
    # the projects "shapefiles" directory
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        pass

    assert sf.shp.closed is True
    assert sf.dbf.closed is True
    assert sf.shx.closed is True

    # check that can read again
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        pass


def test_reader_context_filelike():
    """
    Assert that using the context manager
    leaves the shp, shx, and dbf files open
    on exit, if given filelike objects.
    """
    # note uses an actual shapefile from
    # the projects "shapefiles" directory
    shp = open(f"{shapefiles_dir.as_posix()}/blockgroups.shp", mode="rb")
    shx = open(f"{shapefiles_dir.as_posix()}/blockgroups.shx", mode="rb")
    dbf = open(f"{shapefiles_dir.as_posix()}/blockgroups.dbf", mode="rb")
    with shapefile.Reader(shp=shp, shx=shx, dbf=dbf) as sf:
        pass

    assert sf.shp.closed is False
    assert sf.dbf.closed is False
    assert sf.shx.closed is False

    # check that can read again
    with shapefile.Reader(shp=shp, shx=shx, dbf=dbf) as sf:
        pass


def test_reader_shapefile_type():
    """
    Assert that the type of the shapefile
    is returned correctly.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        assert sf.shapeType == 5  # 5 means Polygon
        assert sf.shapeType == shapefile.POLYGON
        assert sf.shapeTypeName == "POLYGON"


def test_reader_shapefile_length():
    """
    Assert that the length the reader gives us
    matches up with the number of records
    in the file.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        assert len(sf) == len(sf.shapes())


def test_shape_metadata():
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        shape = sf.shape(0)
        assert shape.shapeType == 5  # Polygon
        assert shape.shapeType == shapefile.POLYGON
        assert sf.shapeTypeName == "POLYGON"


def test_reader_fields():
    """
    Assert that the reader's fields attribute
    gives the shapefile's fields as a list.
    Assert that each field has a name,
    type, field length, and decimal length.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        fields = sf.fields
        assert isinstance(fields, list)

        field = fields[0]
        assert isinstance(field[0], str)  # field name
        assert field[1] in ["C", "N", "F", "L", "D", "M"]  # field type
        assert isinstance(field[2], int)  # field length
        assert isinstance(field[3], int)  # decimal length


def test_reader_shapefile_extension_ignored():
    """
    Assert that the filename's extension is
    ignored when reading a shapefile.
    """
    base = f"{shapefiles_dir.as_posix()}/blockgroups"
    ext = ".abc"
    filename = base + ext
    with shapefile.Reader(filename) as sf:
        assert len(sf) == 663

    # assert test.abc does not exist
    assert not os.path.exists(filename)


def test_reader_pathlike():
    """
    Assert that path-like objects can be read.
    """
    with shapefile.Reader(shapefiles_dir / "blockgroups") as sf:
        assert len(sf) == 663


def test_reader_dbf_only():
    """
    Assert that specifying just the
    dbf argument to the shapefile reader
    reads just the dbf file.
    """
    with shapefile.Reader(dbf=f"{shapefiles_dir.as_posix()}/blockgroups.dbf") as sf:
        assert len(sf) == 663
        record = sf.record(3)
        assert record[1:3] == ["060750601001", 4715]


def test_reader_dbf_only_from_Path():
    """
    Assert that specifying just the
    dbf argument to the shapefile reader as a Path
    reads just the dbf file.
    """
    with shapefile.Reader(dbf=shapefiles_dir / "blockgroups.dbf") as sf:
        assert len(sf) == 663
        record = sf.record(3)
        assert record[1:3] == ["060750601001", 4715]


def test_reader_shp_shx_only():
    """
    Assert that specifying just the
    shp and shx argument to the shapefile reader
    reads just the shp and shx file.
    """
    with shapefile.Reader(
        shp=f"{shapefiles_dir.as_posix()}/blockgroups.shp",
        shx=f"{shapefiles_dir.as_posix()}/blockgroups.shx",
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173


def test_reader_shp_shx_only_from_Paths():
    """
    Assert that specifying just the
    shp and shx arguments to the shapefile reader as Paths
    reads just the shp and shx file.
    """
    with shapefile.Reader(
        shp=shapefiles_dir / "blockgroups.shp", shx=shapefiles_dir / "blockgroups.shx"
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173


def test_reader_shp_dbf_only():
    """
    Assert that specifying just the
    shp and dbf arguments to the shapefile reader
    reads just the shp and dbf file.
    """
    with shapefile.Reader(
        shp=f"{shapefiles_dir.as_posix()}/blockgroups.shp",
        dbf=f"{shapefiles_dir.as_posix()}/blockgroups.dbf",
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173
        record = sf.record(3)
        assert record[1:3] == ["060750601001", 4715]


def test_reader_shp_dbf_only_from_Paths():
    """
    Assert that specifying just the
    shp and dbf arguments to the shapefile reader as Paths
    reads just the shp and dbf file.
    """
    with shapefile.Reader(
        shp=shapefiles_dir / "blockgroups.shp", dbf=shapefiles_dir / "blockgroups.dbf"
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173
        record = sf.record(3)
        assert record[1:3] == ["060750601001", 4715]


def test_reader_shp_only():
    """
    Assert that specifying just the
    shp argument to the shapefile reader
    reads just the shp file (shx optional).
    """
    with shapefile.Reader(shp=f"{shapefiles_dir.as_posix()}/blockgroups.shp") as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173


def test_reader_shp_only_from_Path():
    """
    Assert that specifying just the
    shp argument to the shapefile reader as a Path
    reads just the shp file (shx optional).
    """
    with shapefile.Reader(shp=shapefiles_dir / "blockgroups.shp") as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173


def test_reader_filelike_dbf_only():
    """
    Assert that specifying just the
    dbf argument to the shapefile reader
    reads just the dbf file.
    """
    with shapefile.Reader(
        dbf=open(f"{shapefiles_dir.as_posix()}/blockgroups.dbf", "rb")
    ) as sf:
        assert len(sf) == 663
        record = sf.record(3)
        assert record[1:3] == ["060750601001", 4715]


def test_reader_filelike_shp_shx_only():
    """
    Assert that specifying just the
    shp and shx argument to the shapefile reader
    reads just the shp and shx file.
    """
    with shapefile.Reader(
        shp=open(f"{shapefiles_dir.as_posix()}/blockgroups.shp", "rb"),
        shx=open(f"{shapefiles_dir.as_posix()}/blockgroups.shx", "rb"),
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173


def test_reader_filelike_shp_dbf_only():
    """
    Assert that specifying just the
    shp and shx argument to the shapefile reader
    reads just the shp and dbf file.
    """
    with shapefile.Reader(
        shp=open(f"{shapefiles_dir.as_posix()}/blockgroups.shp", "rb"),
        dbf=open(f"{shapefiles_dir.as_posix()}/blockgroups.dbf", "rb"),
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173
        record = sf.record(3)
        assert record[1:3] == ["060750601001", 4715]


def test_reader_filelike_shp_only():
    """
    Assert that specifying just the
    shp argument to the shapefile reader
    reads just the shp file (shx optional).
    """
    with shapefile.Reader(
        shp=open(f"{shapefiles_dir.as_posix()}/blockgroups.shp", "rb")
    ) as sf:
        assert len(sf) == 663
        shape = sf.shape(3)
        assert len(shape.points) == 173


def test_reader_shapefile_delayed_load():
    """
    Assert that both:
      i) reading a shape from an uninitialised Reader() raises ShapefileException and,
      ii) it can still load a shapefile for reading afterwards, via .load(...).
    """
    with shapefile.Reader() as sf:
        # assert that data request raises exception, since no file has been provided yet
        with pytest.raises(shapefile.ShapefileException):
            sf.shape(0)
        # assert that works after loading file manually
        sf.load(f"{shapefiles_dir.as_posix()}/blockgroups")
        assert len(sf) == 663


def test_records_match_shapes():
    """
    Assert that the number of records matches
    the number of shapes in the shapefile.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        records = sf.records()
        shapes = sf.shapes()
        assert len(records) == len(shapes)


def test_record_attributes(fields=None):
    """
    Assert that record retrieves all relevant values and can
    be accessed as attributes and dictionary items.
    """
    # note
    # second element in fields matches first element
    # in record because records dont have DeletionFlag
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        for i in range(len(sf)):
            # full record
            full_record = sf.record(i)
            # user-fetched record
            if fields is not None:
                # only a subset of fields
                record = sf.record(i, fields=fields)
            else:
                # default all fields
                record = full_record
                fields = [
                    field[0] for field in sf.fields[1:]
                ]  # fieldnames, sans del flag
            # check correct length
            assert len(record) == len(set(fields))
            # check record values (should be in same order as shapefile fields)
            i = 0
            for field in sf.fields:
                field_name = field[0]
                if field_name in fields:
                    assert (
                        record[i] == record[field_name] == getattr(record, field_name)
                    )
                    i += 1


def test_record_subfields():
    """
    Assert that reader correctly retrieves only a subset
    of fields when specified.
    """
    fields = ["AREA", "POP1990", "MALES", "FEMALES", "MOBILEHOME"]
    test_record_attributes(fields=fields)


def test_record_subfields_unordered():
    """
    Assert that reader correctly retrieves only a subset
    of fields when specified, given in random order but
    retrieved in the order of the shapefile fields.
    """
    fields = sorted(["AREA", "POP1990", "MALES", "FEMALES", "MOBILEHOME"])
    test_record_attributes(fields=fields)


def test_record_subfields_delflag_notvalid():
    """
    Assert that reader does not consider DeletionFlag as a valid field name.
    """
    fields = ["DeletionFlag", "AREA", "POP1990", "MALES", "FEMALES", "MOBILEHOME"]
    with pytest.raises(ValueError):
        test_record_attributes(fields=fields)


def test_record_subfields_duplicates():
    """
    Assert that reader correctly retrieves only a subset
    of fields when specified, handling duplicate input fields.
    """
    fields = ["AREA", "AREA", "AREA", "MALES", "MALES", "MOBILEHOME"]
    test_record_attributes(fields=fields)
    # check that only 3 values
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        rec = sf.record(0, fields=fields)
        assert len(rec) == len(set(fields))


def test_record_subfields_empty():
    """
    Assert that reader does not retrieve any fields when given
    an empty list.
    """
    fields = []
    test_record_attributes(fields=fields)
    # check that only 0 values
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        rec = sf.record(0, fields=fields)
        assert len(rec) == 0


def test_record_as_dict():
    """
    Assert that a record object can be converted
    into a dictionary and data remains correct.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        record = sf.record(0)
        as_dict = record.as_dict()

        assert len(record) == len(as_dict)
        for key, value in as_dict.items():
            assert record[key] == value


def test_record_oid():
    """
    Assert that the record's oid attribute returns
    its index in the shapefile.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        for i in range(len(sf)):
            record = sf.record(i)
            assert record.oid == i

        for i, record in enumerate(sf.records()):
            assert record.oid == i

        for i, record in enumerate(sf.iterRecords()):
            assert record.oid == i

        for i, shaperec in enumerate(sf.iterShapeRecords()):
            assert shaperec.record.oid == i


@pytest.mark.slow
def test_iterRecords_start_stop():
    """
    Assert that Reader.iterRecords(start, stop)
    returns the correct records, as if searched for
    by index with Reader.record
    """

    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        N = len(sf)

        # Arbitrary selection of record indices
        # (there are 663 records in blockgroups.dbf).
        indices = [
            0,
            1,
            2,
            5,
            11,
            41,
            310,
            513,
            N - 3,
            N - 1,
        ]
        for i, index in enumerate(indices):
            for record in sf.iterRecords(start=index):
                assert record == sf.record(record.oid)

            for record in sf.iterRecords(stop=index):
                assert record == sf.record(record.oid)

            for j in range(i + 1, len(indices)):
                stop = indices[j]
                # test negative indexing from end, as well as
                # positive values of stop, and its default
                for stop_arg in (stop, stop - N):
                    for record in sf.iterRecords(start=index, stop=stop_arg):
                        assert record == sf.record(record.oid)


def test_shape_oid():
    """
    Assert that the shape's oid attribute returns
    its index in the shapefile.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        for i in range(len(sf)):
            shape = sf.shape(i)
            assert shape.oid == i

        for i, shape in enumerate(sf.shapes()):
            assert shape.oid == i

        for i, shape in enumerate(sf.iterShapes()):
            assert shape.oid == i

        for i, shaperec in enumerate(sf.iterShapeRecords()):
            assert shaperec.shape.oid == i


def test_shape_oid_no_shx():
    """
    Assert that the shape's oid attribute returns
    its index in the shapefile, when shx file is missing.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    shp = open(basename + ".shp", "rb")
    dbf = open(basename + ".dbf", "rb")
    with shapefile.Reader(shp=shp, dbf=dbf) as sf:
        with shapefile.Reader(basename) as sf_expected:
            for i in range(len(sf)):
                shape = sf.shape(i)
                assert shape.oid == i
                shape_expected = sf_expected.shape(i)
                assert shape.__geo_interface__ == shape_expected.__geo_interface__, (
                    f"{i=}"
                )

            for i, shape in enumerate(sf.shapes()):
                assert shape.oid == i
                shape_expected = sf_expected.shape(i)
                assert shape.__geo_interface__ == shape_expected.__geo_interface__

            for i, shape in enumerate(sf.iterShapes()):
                assert shape.oid == i
                shape_expected = sf_expected.shape(i)
                assert shape.__geo_interface__ == shape_expected.__geo_interface__

            for i, shaperec in enumerate(sf.iterShapeRecords()):
                assert shaperec.shape.oid == i
                shape_expected = sf_expected.shape(i)
                assert (
                    shaperec.shape.__geo_interface__ == shape_expected.__geo_interface__
                )


def test_reader_offsets():
    """
    Assert that reader will not read the shx offsets unless necessary,
    i.e. requesting a shape index.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    with shapefile.Reader(basename) as sf:
        # shx offsets should not be read during loading
        assert sf.shx_reader._shxRecords_16bw is None
        # reading a shape index should trigger reading all offsets from shx file
        sf.shape(3)
        assert len(sf.shx_reader.offsets) == len(sf.shapes())


def test_reader_offsets_no_shx():
    """
    Assert that reading a shapefile without a shx file will not build
    the offsets unless necessary, i.e. reading all the shapes.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    shp = open(basename + ".shp", "rb")
    dbf = open(basename + ".dbf", "rb")
    with shapefile.Reader(shp=shp, dbf=dbf) as sf:
        # offsets should not be built during loading
        with pytest.raises(shapefile.ShapefileException):
            sf.shx_reader
        # reading a shape index should iterate to the shape
        # but the list of offsets should remain empty
        sf.shape(3)
        with pytest.raises(shapefile.ShapefileException):
            sf.shx_reader
        # reading all the shapes should build the list of shape headers
        shapes = sf.shapes()
        assert len(sf.shp_reader.headers_cache) == len(shapes)


def test_reader_numshapes():
    """
    Assert that reader reads the numShapes attribute from the
    shx file header during loading.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    with shapefile.Reader(basename) as sf:
        # numShapes should be set during loading
        assert sf.numShapes is not None
        # numShapes should equal the number of shapes
        assert sf.numShapes == len(sf.shapes())


def test_reader_numshapes_no_shx():
    """
    Assert that reading a shapefile without a shx file will have
    an unknown value for the numShapes attribute (None), and that
    reading all the shapes will set the numShapes attribute.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    shp = open(basename + ".shp", "rb")
    dbf = open(basename + ".dbf", "rb")
    with shapefile.Reader(shp=shp, dbf=dbf) as sf:
        # numShapes should be unknown due to missing shx file
        assert not sf.numShapes
        # numShapes should be set after reading all the shapes
        shapes = sf.shapes()
        assert sf.numShapes == len(shapes)


def test_reader_len():
    """
    Assert that calling len() on reader is equal to length of
    all shapes and records.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    with shapefile.Reader(basename) as sf:
        assert len(sf) == len(sf.records()) == len(sf.shapes())


def test_reader_len_not_loaded():
    """
    Assert that calling len() on reader that hasn't loaded a shapefile
    yet is equal to 0.
    """
    with shapefile.Reader() as sf:
        assert len(sf) == 0


def test_reader_len_dbf_only():
    """
    Assert that calling len() on reader when reading a dbf file only,
    is equal to length of all records.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    dbf = open(basename + ".dbf", "rb")
    with shapefile.Reader(dbf=dbf) as sf:
        assert len(sf) == len(sf.records())


def test_reader_len_no_dbf():
    """
    Assert that calling len() on reader when dbf file is missing,
    is equal to length of all shapes.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    shp = open(basename + ".shp", "rb")
    shx = open(basename + ".shx", "rb")
    with shapefile.Reader(shp=shp, shx=shx) as sf:
        assert len(sf) == len(sf.shapes())


def test_reader_len_no_dbf_shx():
    """
    Assert that calling len() on reader when dbf and shx file is missing,
    is equal to length of all shapes.
    """
    basename = f"{shapefiles_dir.as_posix()}/blockgroups"
    shp = open(basename + ".shp", "rb")
    with shapefile.Reader(shp=shp) as sf:
        assert len(sf) == len(sf.shapes())


def test_reader_corrupt_files(tmp_path):
    """
    Assert that reader is able to handle corrupt files by
    strictly going off the header information.
    """
    basename = str(tmp_path / "corrupt_too_long")

    # write a shapefile with junk byte data at end of files
    with shapefile.Writer(basename) as w:
        w.field("test", "C", 50)
        # add 10 line geoms
        for _ in range(10):
            w.record("value")
            w.line([[(1, 1), (1, 2), (2, 2)]])
        # add junk byte data to end of dbf and shp files
        w.dbf_writer.file.write(b"12345")
        w.shp.write(b"12345")

    # read the corrupt shapefile and assert that it reads correctly
    with pytest.warns(shapefile.PossiblyCorruptFileHeader):
        with shapefile.Reader(basename) as sf:
            # assert correct shapefile length metadata
            assert len(sf) == 10
            assert sf.numRecords == 10
            assert sf.numShapes == 10
            # assert that records are read without error
            assert len(sf.records()) == 10
            # assert that didn't read the extra junk data
            stopped = sf.dbf.tell()
            sf.dbf.seek(0, 2)
            end = sf.dbf.tell()
            assert (end - stopped) == 5
            # assert that shapes are read without error
            assert len(sf.shapes()) == 10
            # assert that didn't read the extra junk data
            stopped = sf.shp.tell()
            sf.shp.seek(0, 2)
            end = sf.shp.tell()
            assert (end - stopped) == 5


def test_bboxfilter_shape():
    """
    Assert that applying the bbox filter to shape() correctly ignores the shape
    if it falls outside, and returns it if inside.
    """
    inside = [-122.4, 37.8, -122.35, 37.82]
    outside = list(inside)
    outside[0] *= 10
    outside[2] *= 10
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        assert sf.shape(0, bbox=inside) is not None
        assert sf.shape(0, bbox=outside) is None


def test_bboxfilter_shapes():
    """
    Assert that applying the bbox filter to shapes() correctly ignores shapes
    that fall outside, and returns those that fall inside.
    """
    bbox = [-122.4, 37.8, -122.35, 37.82]
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        # apply bbox filter
        shapes = sf.shapes(bbox=bbox)
        # manually check bboxes
        manual = shapefile.Shapes()
        for shape in sf.iterShapes():
            if shapefile.bbox_overlap(shape.bbox, bbox):
                manual.append(shape)
        # compare
        assert len(shapes) == len(manual)
        # check that they line up
        for shape, man in zip(shapes, manual):
            assert shape.oid == man.oid
            assert shape.__geo_interface__ == man.__geo_interface__


def test_bboxfilter_shapes_outside():
    """
    Assert that applying the bbox filter to shapes() correctly returns
    no shapes when the bbox is outside the entire shapefile.
    """
    bbox = [-180, 89, -179, 90]
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        shapes = sf.shapes(bbox=bbox)
        assert len(shapes) == 0


def test_bboxfilter_itershapes():
    """
    Assert that applying the bbox filter to iterShapes() correctly ignores shapes
    that fall outside, and returns those that fall inside.
    """
    bbox = [-122.4, 37.8, -122.35, 37.82]
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        # apply bbox filter
        shapes = list(sf.iterShapes(bbox=bbox))
        # manually check bboxes
        manual = shapefile.Shapes()
        for shape in sf.iterShapes():
            if shapefile.bbox_overlap(shape.bbox, bbox):
                manual.append(shape)
        # compare
        assert len(shapes) == len(manual)
        # check that they line up
        for shape, man in zip(shapes, manual):
            assert shape.oid == man.oid
            assert shape.__geo_interface__ == man.__geo_interface__


def test_bboxfilter_shaperecord():
    """
    Assert that applying the bbox filter to shapeRecord() correctly ignores the shape
    if it falls outside, and returns it if inside.
    """
    inside = [-122.4, 37.8, -122.35, 37.82]
    outside = list(inside)
    outside[0] *= 10
    outside[2] *= 10
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        # inside
        shaperec = sf.shapeRecord(0, bbox=inside)
        assert shaperec is not None
        assert shaperec.shape.oid == shaperec.record.oid
        # outside
        assert sf.shapeRecord(0, bbox=outside) is None


def test_bboxfilter_shaperecords():
    """
    Assert that applying the bbox filter to shapeRecords() correctly ignores shapes
    that fall outside, and returns those that fall inside.
    """
    bbox = [-122.4, 37.8, -122.35, 37.82]
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        # apply bbox filter
        shaperecs = sf.shapeRecords(bbox=bbox)
        # manually check bboxes
        manual = shapefile.ShapeRecords()
        for shaperec in sf.iterShapeRecords():
            if shapefile.bbox_overlap(shaperec.shape.bbox, bbox):
                manual.append(shaperec)
        # compare
        assert len(shaperecs) == len(manual)
        # check that they line up
        for shaperec, man in zip(shaperecs, manual):
            # oids
            assert shaperec.shape.oid == shaperec.record.oid
            # same shape as manual
            assert shaperec.shape.oid == man.shape.oid
            assert shaperec.shape.__geo_interface__ == man.shape.__geo_interface__
            # same record as manual
            assert shaperec.record.oid == man.record.oid
            assert shaperec.record == man.record


def test_bboxfilter_itershaperecords():
    """
    Assert that applying the bbox filter to iterShapeRecords() correctly ignores shapes
    that fall outside, and returns those that fall inside.
    """
    bbox = [-122.4, 37.8, -122.35, 37.82]
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        # apply bbox filter
        shaperecs = list(sf.iterShapeRecords(bbox=bbox))
        # manually check bboxes
        manual = shapefile.ShapeRecords()
        for shaperec in sf.iterShapeRecords():
            if shapefile.bbox_overlap(shaperec.shape.bbox, bbox):
                manual.append(shaperec)
        # compare
        assert len(shaperecs) == len(manual)
        # check that they line up
        for shaperec, man in zip(shaperecs, manual):
            # oids
            assert shaperec.shape.oid == shaperec.record.oid
            # same shape as manual
            assert shaperec.shape.oid == man.shape.oid
            assert shaperec.shape.__geo_interface__ == man.shape.__geo_interface__
            # same record as manual
            assert shaperec.record.oid == man.record.oid
            assert shaperec.record == man.record


def test_shaperecords_shaperecord():
    """
    Assert that shapeRecords returns a list of
    ShapeRecord objects.
    Assert that shapeRecord returns a single
    ShapeRecord at the given index.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        shaperecs = sf.shapeRecords()
        shaperec = sf.shapeRecord(0)
        should_match = shaperecs[0]

        # assert record is equal
        assert shaperec.record == should_match.record

        # assert shape is equal
        shaperec_json = shaperec.shape.__geo_interface__
        should_match_json = should_match.shape.__geo_interface__
        assert shaperec_json == should_match_json


def test_shaperecord_shape():
    """
    Assert that a ShapeRecord object has a shape
    attribute that contains shape data.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        shaperec = sf.shapeRecord(3)
        shape = shaperec.shape
        point = shape.points[0]
        assert len(point) == 2


def test_shaperecord_record():
    """
    Assert that a ShapeRecord object has a record
    attribute that contains record data.
    """
    with shapefile.Reader(f"{shapefiles_dir.as_posix()}/blockgroups") as sf:
        shaperec = sf.shapeRecord(3)
        record = shaperec.record

        assert record[1:3] == ["060750601001", 4715]


def test_reader_zip_polyylinez_no_m_itershaperecords():
    """
    Make sure the M field is initialised to None (so the
    fix from the bug in 3.0.2 isn't regressed)!

    Test Polygonz Shapes can be read, even if the m field is missing
    (all the points in this file are 2D only, so this could also be
    saved as a Polygon / type 5 shapefile instead of the shape type
    15 one it currently is).

    REL.zip included with permission: https://github.com/OpenNHM/AvaFrame/issues/1203#issuecomment-4477589128
    Owner: Open Natural Hazard Modelling
    Original source:  https://github.com/OpenNHM/AvaFrameData/blob/main/avaPopeletzbach/
    License CC-BY-4.0
    """
    with shapefile.Reader(
        f"{shapefiles_dir.as_posix()}/REL.zip/REL/releaseArea20090407"
    ) as sf:
        for _shaperec in sf.iterShapeRecords():
            pass


def test_write_field_name_below_limit(tmpdir):
    filename = tmpdir.join("test.shp").strpath
    with shapefile.Writer(filename, strict=True) as writer:
        writer.field("a" * 5, "C")  # many under length limit
        writer.field("a" * 9, "C")  # 1 under length limit

    with shapefile.Reader(filename) as reader:
        fields = reader.fields[1:]
        assert len(fields[0][0]) == 5
        assert len(fields[1][0]) == 9

def test_write_field_names_above_limit_non_strict(tmpdir):
    filename = tmpdir.join("test.shp").strpath
    with shapefile.Writer(filename, strict=False) as w:
        w.field("a" * 10, "C") # at length limit
        for l in [11, 20]: # 1 over, and twice the limit
            with pytest.warns(shapefile.PossibleDataLoss):
                w.field("a" * l, "C")

    with shapefile.Reader(filename) as reader:
        fields = reader.fields[1:]
        assert len(fields[0][0]) == 10
        assert len(fields[1][0]) == 10
        assert len(fields[2][0]) == 10

def test_write_field_names_above_limit_strict(tmpdir):
    filename = tmpdir.join("test.shp").strpath
    with shapefile.Writer(filename, strict=True) as writer:
        writer.field("a" * 10, "C") # at length limit
        for l in [11, 20]: # at 1 over length limitand twice the limit
            with pytest.raises(ValueError):
                writer.field("a" * l, "C")



def test_write_shp_only(tmpdir):
    """
    Assert that specifying just the
    shp argument to the shapefile writer
    creates just a shp file.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(shp=filename + ".shp") as writer:
        writer.point(1, 1)
    assert writer.shp and not writer._shx and not writer._dbf
    assert writer.shpNum == 1
    assert len(writer) == 1
    assert writer.shp.closed is True

    # assert test.shp exists
    assert os.path.exists(filename + ".shp")

    # test that can read shapes
    with shapefile.Reader(shp=filename + ".shp") as reader:
        assert reader._shp and not reader._shx and not reader._dbf
        assert (reader.numRecords, reader.numShapes) == (None, 0)
        # numShapes is unknown in the absence of shx file
        assert len(reader.shapes()) == 1

    # assert test.shx does not exist
    assert not os.path.exists(filename + ".shx")

    # assert test.dbf does not exist
    assert not os.path.exists(filename + ".dbf")


def test_write_shp_shx_only(tmpdir):
    """
    Assert that specifying just the shp and
    shx argument to the shapefile writer
    creates just a shp and shx file.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(shp=filename + ".shp", shx=filename + ".shx") as writer:
        writer.point(1, 1)
    assert writer.shp and writer.shx and not writer._dbf
    assert writer.shpNum == 1
    assert len(writer) == 1
    assert writer.shp.closed is writer.shx.closed is True

    # assert test.shp exists
    assert os.path.exists(filename + ".shp")

    # assert test.shx exists
    assert os.path.exists(filename + ".shx")

    # test that can read shapes and offsets
    with shapefile.Reader(shp=filename + ".shp", shx=filename + ".shx") as reader:
        assert reader.shp and reader.shx and not reader._dbf
        assert (reader.numRecords, reader.numShapes) == (None, 1)
        reader.shape(0)  # trigger reading of shx offsets
        assert len(reader.shx_reader.offsets) == 1
        assert len(reader.shapes()) == 1

    # assert test.dbf does not exist
    assert not os.path.exists(filename + ".dbf")


def test_write_shp_dbf_only(tmpdir):
    """
    Assert that specifying just the
    shp and dbf argument to the shapefile writer
    creates just a shp and dbf file.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(shp=filename + ".shp", dbf=filename + ".dbf") as writer:
        writer.field("field1", "C")  # required to create a valid dbf file
        writer.record("value")
        writer.point(1, 1)
    assert writer.shp and not writer._shx and writer.dbf
    assert writer.shpNum == writer.recNum == 1
    assert len(writer) == 1
    assert writer.shp.closed is writer.dbf.closed is True

    # assert test.shp exists
    assert os.path.exists(filename + ".shp")

    # assert test.dbf exists
    assert os.path.exists(filename + ".dbf")

    # test that can read records and shapes
    with shapefile.Reader(shp=filename + ".shp", dbf=filename + ".dbf") as reader:
        assert reader.shp and not reader._shx and reader.dbf
        assert (reader.numRecords, reader.numShapes) == (1, 0)
        # numShapes is unknown in the absence of shx file
        assert len(reader.records()) == 1
        assert len(reader.shapes()) == 1

    # assert test.shx does not exist
    assert not os.path.exists(filename + ".shx")


def test_write_dbf_only(tmpdir):
    """
    Assert that specifying just the
    dbf argument to the shapefile writer
    creates just a dbf file.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(dbf=filename + ".dbf") as writer:
        writer.field("field1", "C")  # required to create a valid dbf file
        writer.record("value")
    assert not writer._shp and not writer._shx and writer.dbf
    assert writer.recNum == 1
    assert len(writer) == 1
    assert writer.dbf.closed is True

    # assert test.dbf exists
    assert os.path.exists(filename + ".dbf")

    # test that can read records
    with shapefile.Reader(dbf=filename + ".dbf") as reader:
        assert not reader._shp and not reader._shx and reader.dbf
        assert (reader.numRecords, reader.numShapes) == (1, 0)
        assert len(reader.records()) == 1

    # assert test.shp does not exist
    assert not os.path.exists(filename + ".shp")

    # assert test.shx does not exist
    assert not os.path.exists(filename + ".shx")


def test_write_default_shp_shx_dbf(tmpdir):
    """
    Assert that creating the shapefile writer without
    specifying the shp, shx, or dbf arguments
    creates a set of shp, shx, and dbf files.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(filename) as writer:
        writer.field("field1", "C")  # required to create a valid dbf file
        writer.record("value")
        writer.null()

    # assert shp, shx, dbf files exist
    assert os.path.exists(filename + ".shp")
    assert os.path.exists(filename + ".shx")
    assert os.path.exists(filename + ".dbf")


def test_write_pathlike(tmpdir):
    """
    Assert that path-like objects can be written.
    Similar to test_write_default_shp_shx_dbf.
    """
    filename = tmpdir.join("test")
    assert not isinstance(filename, str)
    with shapefile.Writer(filename) as writer:
        writer.field("field1", "C")
        writer.record("value")
        writer.null()
    assert (filename + ".shp").ensure()
    assert (filename + ".shx").ensure()
    assert (filename + ".dbf").ensure()


def test_write_filelike(tmpdir):
    """
    Assert that file-like objects are written correctly.
    """
    shp = open(tmpdir.join("test.shp").strpath, mode="wb+")
    shx = open(tmpdir.join("test.shx").strpath, mode="wb+")
    dbf = open(tmpdir.join("test.dbf").strpath, mode="wb+")
    with shapefile.Writer(shx=shx, dbf=dbf, shp=shp) as writer:
        writer.field("field1", "C")  # required to create a valid dbf file
        writer.record("value")
        writer.null()

    # test that filelike objects were written correctly
    with shapefile.Reader(shp=shp, shx=shx, dbf=dbf) as reader:
        assert len(reader) == 1
        assert reader.shape(0).shapeType == shapefile.NULL


def test_write_close_path(tmpdir):
    """
    Assert that the Writer close() method
    closes the shp, shx, and dbf files
    on exit, if given paths.
    """
    sf = shapefile.Writer(tmpdir.join("test"))
    sf.field("field1", "C")  # required to create a valid dbf file
    sf.record("value")
    sf.null()
    sf.close()

    assert sf.shp.closed is True
    assert sf.dbf.closed is True
    assert sf.shx.closed is True

    # test that opens and reads correctly after
    with shapefile.Reader(tmpdir.join("test")) as reader:
        assert len(reader) == 1
        assert reader.shape(0).shapeType == shapefile.NULL


def test_write_close_filelike(tmpdir):
    """
    Assert that the Writer close() method
    leaves the shp, shx, and dbf files open
    on exit, if given filelike objects.
    """
    shp = open(tmpdir.join("test.shp").strpath, mode="wb+")
    shx = open(tmpdir.join("test.shx").strpath, mode="wb+")
    dbf = open(tmpdir.join("test.dbf").strpath, mode="wb+")
    sf = shapefile.Writer(shx=shx, dbf=dbf, shp=shp)
    sf.field("field1", "C")  # required to create a valid dbf file
    sf.record("value")
    sf.null()
    sf.close()

    assert sf.shp.closed is False
    assert sf.dbf.closed is False
    assert sf.shx.closed is False

    # test that opens and reads correctly after
    with shapefile.Reader(shx=shx, dbf=dbf, shp=shp) as reader:
        assert len(reader) == 1
        assert reader.shape(0).shapeType == shapefile.NULL


def test_write_context_path(tmpdir):
    """
    Assert that the Writer context manager
    closes the shp, shx, and dbf files
    on exit, if given paths.
    """
    with shapefile.Writer(tmpdir.join("test")) as sf:
        sf.field("field1", "C")  # required to create a valid dbf file
        sf.record("value")
        sf.null()

    assert sf.shp.closed is True
    assert sf.dbf.closed is True
    assert sf.shx.closed is True

    # test that opens and reads correctly after
    with shapefile.Reader(tmpdir.join("test")) as reader:
        assert len(reader) == 1
        assert reader.shape(0).shapeType == shapefile.NULL


def test_write_context_filelike(tmpdir):
    """
    Assert that the Writer context manager
    leaves the shp, shx, and dbf files open
    on exit, if given filelike objects.
    """
    shp = open(tmpdir.join("test.shp").strpath, mode="wb+")
    shx = open(tmpdir.join("test.shx").strpath, mode="wb+")
    dbf = open(tmpdir.join("test.dbf").strpath, mode="wb+")
    with shapefile.Writer(shx=shx, dbf=dbf, shp=shp) as sf:
        sf.field("field1", "C")  # required to create a valid dbf file
        sf.record("value")
        sf.null()

    assert sf.shp.closed is False
    assert sf.dbf.closed is False
    assert sf.shx.closed is False

    # test that opens and reads correctly after
    with shapefile.Reader(shx=shx, dbf=dbf, shp=shp) as reader:
        assert len(reader) == 1
        assert reader.shape(0).shapeType == shapefile.NULL


def test_write_shapefile_extension_ignored(tmpdir):
    """
    Assert that the filename's extension is
    ignored when creating a shapefile.
    """
    base = "test"
    ext = ".abc"
    filename = tmpdir.join(base + ext).strpath
    with shapefile.Writer(filename) as writer:
        writer.field("field1", "C")  # required to create a valid dbf file

    # assert shp, shx, dbf files exist
    basepath = tmpdir.join(base).strpath
    assert os.path.exists(basepath + ".shp")
    assert os.path.exists(basepath + ".shx")
    assert os.path.exists(basepath + ".dbf")

    # assert test.abc does not exist
    assert not os.path.exists(basepath + ext)


def test_write_record(tmpdir):
    """
    Test that .record() correctly writes a record using either a list of *args
    or a dict of **kwargs.
    """
    filename = tmpdir.join("test.shp").strpath
    with shapefile.Writer(filename) as writer:
        writer.autoBalance = True

        writer.field("one", "C")
        writer.field("two", "C")
        writer.field("three", "C")
        writer.field("four", "C")

        values = ["one", "two", "three", "four"]
        writer.record(*values)
        writer.record(*values)

        valuedict = dict(zip(values, values))
        writer.record(**valuedict)
        writer.record(**valuedict)

    with shapefile.Reader(filename) as reader:
        for record in reader.iterRecords():
            assert record == values


def test_write_partial_record(tmpdir):
    """
    Test that .record() correctly writes a partial record (given only some of the values)
    using either a list of *args or a dict of **kwargs. Should fill in the gaps.
    """
    filename = tmpdir.join("test.shp").strpath
    with shapefile.Writer(filename) as writer:
        writer.autoBalance = True

        writer.field("one", "C")
        writer.field("two", "C")
        writer.field("three", "C")
        writer.field("four", "C")

        values = ["one", "two"]
        writer.record(*values)
        writer.record(*values)

        valuedict = dict(zip(values, values))
        writer.record(**valuedict)
        writer.record(**valuedict)

    with shapefile.Reader(filename) as reader:
        expected = list(values)
        expected.extend(["", ""])
        for record in reader.iterRecords():
            assert record == expected

        assert len(reader.records()) == 4


def test_write_geojson(tmpdir):
    """
    Assert that the output of geo interface can be written to json.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(filename) as w:
        w.field("TEXT", "C")
        w.field("NUMBER", "N")
        w.field("DATE", "D")
        w.record("text", 123, datetime.date(1898, 1, 30))
        w.record("text", 123, [1998, 1, 30])
        w.record("text", 123, "19980130")
        w.record("text", 123, "-9999999")  # faulty date
        w.record(None, None, None)
        w.null()
        w.null()
        w.null()
        w.null()
        w.null()

    with shapefile.Reader(filename) as r:
        for feat in r:
            assert json.dumps(feat.__geo_interface__)
        assert json.dumps(r.shapeRecords().__geo_interface__)
        assert json.dumps(r.__geo_interface__)


shape_types = [
    k for k in shapefile.SHAPETYPE_LOOKUP.keys() if k != 31
]  # exclude multipatch


@pytest.mark.parametrize("shape_type", shape_types)
def test_write_empty_shapefile(tmpdir, shape_type):
    """
    Assert that can write an empty shapefile, for all different shape types.
    """
    filename = tmpdir.join("test").strpath
    with shapefile.Writer(filename, shapeType=shape_type) as w:
        w.field("field1", "C")  # required to create a valid dbf file

    with shapefile.Reader(filename) as r:
        # test correct shape type
        assert r.shapeType == shape_type
        # test length 0
        assert len(r) == r.numRecords == r.numShapes == 0
        # test records are empty
        for record in r.iterRecords():
            pass
        assert len(r.records()) == 0
        # test shapes are empty
        assert len(r.shapes()) == 0


def test_write_multipatch(tmpdir):
    """Duplicates one of the doctests that gets filtered out"""
    w = shapefile.Writer(tmpdir / "multipatch")
    w.field("name", "C")

    w.multipatch(
        [
            [
                [0, 0, 0],
                [0, 0, 3],
                [5, 0, 0],
                [5, 0, 3],
                [5, 5, 0],
                [5, 5, 3],
                [0, 5, 0],
                [0, 5, 3],
                [0, 0, 0],
                [0, 0, 3],
            ],  # TRIANGLE_STRIP for house walls
            [
                [2.5, 2.5, 5],
                [0, 0, 3],
                [5, 0, 3],
                [5, 5, 3],
                [0, 5, 3],
                [0, 0, 3],
            ],  # TRIANGLE_FAN for pointed house roof
        ],
        partTypes=[shapefile.TRIANGLE_STRIP, shapefile.TRIANGLE_FAN],
    )  # one type for each part

    w.record("house1")

    w.close()

DATES = [datetime.date(*triple) for triple in [
    (2000,1,1),
]]

@pytest.mark.parametrize("expected_date", DATES)
def test_round_trip_dbf_date_record(expected_date):
    stream = io.BytesIO()
    dbf_w = shapefile.DbfWriter(dbf=stream)
    dbf_w.field("Date","D")
    dbf_w.record(expected_date)
    dbf_w.close()

    dbf_r = shapefile.DbfReader(dbf=stream)
    dbf_r.record(0)[0] == expected_date
    dbf_r.close()

FIELD_VALUE_ERRORS = [
    (" ", 1, "utf-8", "strict"),
]

@pytest.mark.parametrize("value,encoded_len,codec,errors", FIELD_VALUE_ERRORS)
def test_encode_dbf_field_padding_bytes_errors(value,encoded_len,codec,errors):
    s = io.BytesIO()
    w = shapefile.DbfWriter(dbf=s, encoding=codec, encodingErrors=errors, strict=True)
    w.field("name","C", size=len(value))
    with pytest.raises(shapefile.DbfStringDataLoss):
        w.record(value)
    w.close()

LONG_FIELD_NAMES = [
    ("ÀÀÀÀ०", 8, "utf-8", "strict"),  # Encoded bytes are corrupted if truncated to 10 bytes
]

@pytest.mark.parametrize("name,encoded_len,codec,errors", LONG_FIELD_NAMES)
def test_encode_dbf_field_name_truncation(name,encoded_len,codec,errors):
    stream = io.BytesIO()
    w = shapefile.DbfWriter(
        stream,
        encoding=codec,
        encodingErrors=errors,
        strict = False,
        )
    with pytest.warns(shapefile.PossibleDataLoss):
        w.field(name=name)
    field = w.fields[0]
    assert name.startswith(field.name)
    assert len(w.fields[0].name.encode(codec, errors)) == encoded_len
    w.close()

    r = shapefile.DbfReader(stream, encoding=codec, encodingErrors=errors, strict=False)
    assert r.fields[1].name == field.name
    r.close()


TEST_ENCODING_WARNINGS_FIELD_NAMES = [
    ("A", 2, "utf-16-le", "strict"),  # Encoded bytes end in null byte (second byte in low end UTF16 code unit)
    ("ABC", 6, "utf-16-le", "strict"),  # Encoded bytes end in null byte (second byte in low end UTF16 code unit)
    ("ABCDE", 10, "utf-16-le", "strict"),  # Encoded bytes end in null byte (second byte in low end UTF16 code unit)
]

@pytest.mark.parametrize("name,encoded_len,codec,errors", TEST_ENCODING_WARNINGS_FIELD_NAMES)
def test_encode_dbf_field_name_padding(name,encoded_len,codec,errors):
    stream = io.BytesIO()
    w = shapefile.DbfWriter(
        stream,
        encoding=codec,
        encodingErrors=errors,
        strict = True,
        )
    w.field(name=name)
    field = w.fields[0]
    assert name.startswith(field.name)
    assert len(w.fields[0].name.encode(codec, errors)) == encoded_len
    w.close()

    with pytest.warns(shapefile.PossibleDataLoss):
        r = shapefile.DbfReader(stream, encoding=codec, encodingErrors=errors, strict=False)
    assert r.fields[1].name == field.name
    r.close()

NON_ASCII_FIELD_NAMES = [
    ("囊萤映雪", 8, 'utf-16-be', "strict"), # Issue 421.  Encoded bytes contain an ascii space (0x20) so by applying
                                           # encoded.replace(b" ",b"_") the text is corrupted from
                                           # "囊萤映雪" ("Studying by the light of fireflies and snow")
                                           # to: "囊萤晟雪" ("Gathering Fireflies and Flourishing Snow")
                                           # (English translation from Google Translate).
]

@pytest.mark.parametrize("name,encoded_len,codec,errors", NON_ASCII_FIELD_NAMES)
def test_encode_dbf_field_name_corruption(name,encoded_len,codec,errors):
    stream = io.BytesIO()
    w = shapefile.DbfWriter(
        stream,
        encoding=codec,
        encodingErrors=errors,
        strict = True,
        )
    w.field(name=name)
    field = w.fields[0]
    assert name.startswith(field.name)
    assert len(w.fields[0].name.encode(codec, errors)) == encoded_len
    w.close()

    r = shapefile.DbfReader(stream, encoding=codec, encodingErrors=errors, strict=False)
    assert r.fields[1].name == field.name
    r.close()

TEST_STR_VALUES = LONG_FIELD_NAMES + TEST_ENCODING_WARNINGS_FIELD_NAMES + NON_ASCII_FIELD_NAMES

@pytest.mark.parametrize("value,encoded_len,codec,errors", TEST_STR_VALUES)
def test_encode_dbf_field_values(value,encoded_len,codec,errors):
    stream = io.BytesIO()
    w = shapefile.DbfWriter(
        stream,
        encoding=codec,
        encodingErrors=errors,
        strict = False,
        )
    w.field("name", "C")
    w.record(value)
    w.close()
    WARNS = codec.lower() == "utf-16-le" and value.isascii()
    context = pytest.warns(shapefile.PossibleDataLoss) if WARNS else contextlib.nullcontext()
    with context:
        r = shapefile.DbfReader(stream, encoding=codec, encodingErrors=errors, strict=False)
        assert r.record(0)[0] == value
    r.close()

@pytest.fixture
def tmp_latin1_shapefile_shp(tmp_path):
    name = "latin1"
    test_shapefile_dir = tmp_path / name
    test_shapefile_dir.mkdir()
    for file in shapefiles_dir.glob("latin1.*"):
        shutil.copy(file, test_shapefile_dir)
    test_shapefile = test_shapefile_dir / f"{name}.shp"
    return test_shapefile

ENCODINGS_AND_CONTEXTS = [
    ("latin1", contextlib.nullcontext()),
    ("utf8", pytest.raises(shapefile.dbfFileException)),
]
@pytest.mark.parametrize("encoding, context", ENCODINGS_AND_CONTEXTS)
def test_read_latin1_shapefile(encoding, context, tmp_latin1_shapefile_shp):
    """ Extend the smoke test in README.md doctests """

    assert tmp_latin1_shapefile_shp.is_file()

    r = shapefile.Reader(tmp_latin1_shapefile_shp, encoding=encoding)
    with context:
        rec = r.record(0)
    r.close()
    if encoding == "latin1":
        assert rec == [2, u'Ñandú']

@pytest.mark.parametrize("encoding, context", ENCODINGS_AND_CONTEXTS)
def test_read_latin1_shapefile_cpg_file(encoding, context, tmp_latin1_shapefile_shp):
    """ Extend the smoke test in README.md doctests """

    assert tmp_latin1_shapefile_shp.is_file()

    cpg_file = tmp_latin1_shapefile_shp.with_suffix(".cpg")
    cpg_file.write_text(encoding.upper().replace("_","-"))

    r = shapefile.Reader(tmp_latin1_shapefile_shp)
    with context:
        rec = r.record(0)
    r.close()
    if encoding == "latin1":
        assert rec == [2, u'Ñandú']


# ---------------------------------------------------------------------------
# dBASE III memo fields ('M', stored in a companion .dbt file)
# ---------------------------------------------------------------------------

MEMO_BLOCK_SIZE = 512


def _write_memo_shapefile(target):
    """Writes a shapefile with two 'M' fields and four records, including
    blank memos, non-string values and memos spanning several .dbt blocks."""
    long_text = "X" * 1300
    unicode_text = "中文 memo — café naïve 😀 " + "y" * 600
    writer = shapefile.Writer(target, shapeType=shapefile.POINT, autoBalance=True)
    writer.field("id", "N", size=10, decimal=0)
    writer.field("note", "M", size=50)  # requested width must be ignored
    writer.field("other", "C", size=20)
    writer.field("note2", "M")
    rows = [
        (1, "first memo", "a", "second-field memo"),
        (2, None, "b", long_text),
        (3, "", "c", unicode_text),
        (4, 12345, "d", None),  # non-strings are stringified like C fields
    ]
    for i, row in enumerate(rows):
        writer.record(*row)
        writer.point(i, i)
    writer.close()
    return rows, long_text, unicode_text


def test_memo_field_is_always_10_bytes(tmp_path):
    target = tmp_path / "m"
    with shapefile.Writer(target, shapeType=shapefile.NULL, autoBalance=True) as w:
        w.field("wide", "M", size=50, decimal=3)
        assert w.fields[-1].size == 10
        assert w.fields[-1].decimal == 0
        w.record("x")
        w.null()
    with shapefile.Reader(target) as r:
        assert [f for f in r.fields if f.name == "wide"][0].size == 10
        assert r.record(0).wide == "x"


def test_memo_roundtrip_via_all_record_access_paths(tmp_path):
    target = tmp_path / "m"
    rows, long_text, unicode_text = _write_memo_shapefile(target)

    with shapefile.Reader(target) as r:
        assert r.record(0).note == "first memo"
        assert r.record(0).note2 == "second-field memo"
        recs = r.records()
        assert recs[1].note is None
        assert recs[1].note2 == long_text
        assert recs[2].note is None  # '' and None both read back as None
        assert recs[2].note2 == unicode_text
        assert recs[3].note == "12345"
        assert recs[3].note2 is None

        # iterRecords with start/stop and memo field filtering
        iter_recs = list(r.iterRecords(start=1, stop=3, fields=["note2"]))
        assert iter_recs[0].note2 == long_text
        assert not hasattr(iter_recs[0], "note")

        # shapeRecords and __geo_interface__ expose memo values too
        assert r.shapeRecords()[1].record.note2 == long_text
        features = r.__geo_interface__["features"]
        assert features[3]["properties"]["note"] == "12345"
        assert features[2]["properties"]["note2"] == unicode_text


def test_memo_dbt_on_disk_layout_and_version_byte(tmp_path):
    target = tmp_path / "m"
    _write_memo_shapefile(target)

    dbf = target.with_suffix(".dbf").read_bytes()
    dbt = target.with_suffix(".dbt").read_bytes()
    # version byte declares dBASE III with memos
    assert dbf[0] == 0x83
    # block 0 is the 512-byte file header; first 4 bytes = next free block
    assert len(dbt) % MEMO_BLOCK_SIZE == 0
    next_free = struct.unpack("<I", dbt[:4])[0]
    assert next_free == len(dbt) // MEMO_BLOCK_SIZE
    assert dbt[4:MEMO_BLOCK_SIZE] == b"\x00" * (MEMO_BLOCK_SIZE - 4)
    # every memo body is terminated by two 0x1A and padded to a block boundary
    assert dbt[MEMO_BLOCK_SIZE:].count(b"\x1a\x1a") >= 4


def test_memo_dbt_created_for_dbf_path_even_without_records(tmp_path):
    target = tmp_path / "empty"
    with shapefile.Writer(dbf=str(target.with_suffix(".dbf"))) as w:
        w.field("m", "M")
    dbt = target.with_suffix(".dbt")
    assert dbt.exists()
    assert dbt.read_bytes() == struct.pack("<I", 1) + b"\x00" * (
        MEMO_BLOCK_SIZE - 4
    )
    with shapefile.Reader(str(target.with_suffix(".dbf"))) as r:
        assert len(r) == 0
        user_fields = [f for f in r.fields if f.name != "DeletionFlag"]
        assert user_fields == [("m", "M", 10, 0)]


def test_memo_no_memo_fields_keeps_old_output(tmp_path):
    target = tmp_path / "plain"
    with shapefile.Writer(target, shapeType=shapefile.POINT, autoBalance=True) as w:
        w.field("id", "N", 10, 0)
        w.field("name", "C", 20)
        w.record(1, "abc")
        w.point(1, 1)
    assert target.with_suffix(".dbf").read_bytes()[0] == 0x03
    assert not target.with_suffix(".dbt").exists()


def test_memo_missing_dbt_is_lazy_error(tmp_path):
    target = tmp_path / "m"
    _write_memo_shapefile(target)
    target.with_suffix(".dbt").unlink()

    # opening must not fail (same behaviour as a missing .shx)
    r = shapefile.Reader(target)
    try:
        # non-memo fields are still readable ...
        assert r.record(0, fields=["id", "other"]).other == "a"
        assert list(r.iterRecords(fields=["id"]))[3].id == 4
        # ... but touching an 'M' value without .dbt raises
        with pytest.raises(shapefile.dbfFileException):
            r.record(0).note
        with pytest.raises(shapefile.dbfFileException):
            r.records()
    finally:
        r.close()


def test_memo_uppercase_extension_is_found(tmp_path):
    target = tmp_path / "up"
    _write_memo_shapefile(target)
    dbt = target.with_suffix(".dbt")
    dbt.rename(target.with_suffix(".DBT"))
    with shapefile.Reader(target) as r:
        assert r.record(0).note == "first memo"


def test_memo_zip_contains_and_loads_dbt(tmp_path):
    src = tmp_path / "m"
    _write_memo_shapefile(src)
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for ext in (".shp", ".shx", ".dbf", ".dbt"):
            z.write(src.with_suffix(ext), arcname="m" + ext)

    # full member path ...
    with shapefile.Reader(str(archive) + "/m.shp") as r:
        assert r.record(0).note2 == "second-field memo"
    # ... and archive-only form
    with shapefile.Reader(archive) as r:
        assert r.record(0).note == "first memo"


def test_memo_writer_requires_sink_for_memo_records():
    # dbf is an in-memory file object: nowhere to put a sibling .dbt
    w = shapefile.Writer(dbf=io.BytesIO())
    w.field("m", "M")
    with pytest.raises(shapefile.dbfFileException):
        w.record("content would be lost")
    # cleanup must not raise the same error again
    w.close()


def test_memo_writer_dbt_file_object_and_ownership():
    dbf, dbt = io.BytesIO(), io.BytesIO()
    with shapefile.Writer(dbf=dbf, dbt=dbt) as w:
        w.field("m", "M")
        w.record("kept in the caller's stream")
    # user-supplied file objects stay open and are closed by the user
    assert not dbf.closed and not dbt.closed
    dbf.seek(0)
    dbt.seek(0)
    with shapefile.Reader(dbf=dbf, dbt=dbt) as r:
        assert r.record(0).m == "kept in the caller's stream"
    assert not dbf.closed and not dbt.closed
    dbf.close()
    dbt.close()


def test_memo_path_writer_closes_dbt(tmp_path):
    target = tmp_path / "own"
    w = shapefile.Writer(target, shapeType=shapefile.POINT, autoBalance=True)
    w.field("m", "M")
    w.record("x")
    w.point(0, 0)
    dbt_file = w.dbf_writer._get_dbt_writer().file
    assert not dbt_file.closed
    w.close()
    assert dbt_file.closed


def test_memo_writer_constructor_arguments_conflict(tmp_path):
    target = tmp_path / "t"
    with pytest.raises(TypeError):
        shapefile.Writer(target, dbt=io.BytesIO())
    _write_memo_shapefile(target)
    with pytest.raises(TypeError):
        shapefile.Reader(target, dbt=io.BytesIO())
    # a dbt stream without a dbf makes no sense
    with pytest.raises(shapefile.ShapefileException):
        shapefile.Writer(shp=io.BytesIO(), shapeType=shapefile.NULL,
                         dbt=io.BytesIO())


def test_memo_dbf_package_interop(tmp_path):
    """PyPI 'dbf' can read memos pyshp writes (and append to the table),
    and pyshp can read dBASE III memos written by 'dbf'."""
    dbf = pytest.importorskip("dbf")

    target = tmp_path / "from_pyshp.dbf"
    long_one = "A" * 1200
    with shapefile.Writer(dbf=str(target)) as w:
        w.field("id", "N", 10, 0)
        w.field("title", "C", 30)
        w.field("memo1", "M")
        w.field("memo2", "M")
        w.record(1, "first", "hello memo", long_one)
        w.record(2, "second", None, "中文—café")
    assert target.read_bytes()[0] == 0x83

    table = dbf.Table(str(target), codepage="utf8")
    table.open(dbf.READ_WRITE)
    try:
        rows = list(table)
        assert rows[0].memo1.strip() == "hello memo"
        assert rows[0].memo2.strip() == long_one
        assert rows[1].memo2.strip() == "中文—café"
        table.append((3, "appended", "new memo from dbf", "B" * 1300))
    finally:
        table.close()

    with shapefile.Reader(target) as r:
        recs = r.records()
        assert recs[0].memo1 == "hello memo"
        assert recs[0].memo2 == long_one
        assert recs[1].memo2 == "中文—café"
        assert recs[2].memo1 == "new memo from dbf"
        assert recs[2].memo2 == "B" * 1300

    target2 = tmp_path / "from_dbf.dbf"
    table = dbf.Table(
        str(target2), "id N(10,0); title C(30); memo1 M; memo2 M", codepage="utf8"
    )
    table.open(dbf.READ_WRITE)
    try:
        table.append((10, "ten", "dbf-created memo", "x" * 1100))
        table.append((11, "eleven", "", "unicode: 中文 😀"))
    finally:
        table.close()
    assert target2.read_bytes()[0] == 0x83

    with shapefile.Reader(target2) as r:
        recs = r.records()
        assert recs[0].ID == 10
        assert recs[0].MEMO1 == "dbf-created memo"
        assert recs[0].MEMO2 == "x" * 1100
        assert recs[1].MEMO1 == ""
        assert recs[1].MEMO2 == "unicode: 中文 😀"


