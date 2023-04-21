import logging
import warnings
import rioxarray
import pyproj
import xarray as xr
import numpy as np
from datetime import datetime
from typing import (
    Tuple,
    Dict,
    TypedDict,
    Union,
    Any,
    Optional,
)
from numbers import Number
from xarray_data_accessor.shared_types import (
    BoundingBoxDict,
)
from xarray_data_accessor.data_accessors.base import (
    DataAccessorBase,
)


def apply_kwargs(
    accessor_object: DataAccessorBase,
    accessor_kwargs_dict: TypedDict,
    kwargs_dict: Dict[str, Any],
) -> None:
    """Updates the accessor object by parsing kwargs.

    Arguments:
        accessor_object: The accessor object (self).
        accessor_kwargs_dict: A TypedDict storing usable kwargs and types.
        kwargs_dict: The kwargs passed via get_xarray_data().

    Returns:
        None - this should be used to updated the accessor object.
    """
    # if kwargs are buried, dig them out
    while 'kwargs' in kwargs_dict.keys():
        kwargs_dict = kwargs_dict['kwargs']

    # get the TypedDict as a normal dict
    accessor_kwargs_dict = accessor_kwargs_dict.__annotations__

    # apply all kwargs that are in the TypedDict and match the type
    for key, value in kwargs_dict.items():
        if key not in accessor_kwargs_dict.keys():
            warnings.warn(
                f'Kwarg: {key} is allowed valid for {accessor_object.__name__}.'
            )
        elif not isinstance(value, accessor_kwargs_dict[key]):
            warnings.warn(
                f'Kwarg: {key} should be of type {accessor_kwargs_dict[key]}.'
            )
        else:
            setattr(accessor_object, key, value)


def combine_variables(
    dataset_dict: Dict[str, xr.Dataset],
    attrs_dict: Dict[str, Union[str, Number]],
    epsg: int = 4326,
) -> xr.Dataset:
    """Combines all variables into a single dataset."""
    # remove and warn about NoneType responses
    del_keys = []
    for k, v in dataset_dict.items():
        if v is None:
            del_keys.append(k)
        else:
            # write new metadata
            dataset_dict[k].attrs = attrs_dict

    if len(del_keys) > 0:
        warnings.warn(
            f'Could not get data for the following variables: {del_keys}'
        )
        for k in del_keys:
            dataset_dict.pop(k)

    # if just one variable, return the dataset
    if len(dataset_dict) == 0:
        raise ValueError(
            f'A problem occurred! No data was returned.'
        )

    # combine the data from multiple sources
    logging.info('Combining all variable Datasets...')
    out_ds = xr.merge(
        list(dataset_dict.values()),
    ).rio.write_crs(epsg)
    logging.info('Done! Returning combined dataset.')
    return out_ds


def write_crs(
    ds: xr.Dataset,
) -> xr.Dataset:
    # convert spatial_ref naming convention to crs
    if 'spatial_ref' in ds.data_vars:
        ds = ds.rename({'spatial_ref': 'crs'})
    if 'crs' in ds.data_vars:
        # get the epsg code
        epsg_code = pyproj.CRS.from_wkt(
            ds.crs.spatial_ref,
        ).to_epsg()
    else:
        warnings.warn(
            'No CRS variable found in dataset. Assuming EPSG:4326.'
        )
        epsg_code = 4326

    # update the dataset attrs if necessary
    if epsg_code != 4326:
        ds.attrs['EPSG'] = epsg_code

    # write the crs and return the dataset
    ds = ds.rio.write_crs(epsg_code)
    return ds


def crop_data(
    ds: xr.Dataset,
    bbox: BoundingBoxDict,
    xy_dim_names: Optional[Tuple[str, str]] = None,
) -> xr.Dataset:
    """Crops AWS ERA5 to the nearest 0.25 resolution"""
    # get the x/y dim names
    if xy_dim_names:
        x_dim, y_dim = xy_dim_names
    else:
        x_dim = ds.attrs['x_dim']
        y_dim = ds.attrs['y_dim']

    # make sure we have inclusive bounds at 0.25
    x_bounds = np.array([bbox['west'], bbox['east']])
    y_bounds = np.array([bbox['south'], bbox['north']])

    # find closest x, y values in the data
    nearest_x_idxs = np.abs(
        ds[x_dim].values - x_bounds.reshape(-1, 1)
    ).argmin(axis=1)
    nearest_y_idxs = np.abs(
        ds[y_dim].values - y_bounds.reshape(-1, 1)
    ).argmin(axis=1)

    # return the sliced dataset
    return ds.isel(
        {
            x_dim: slice(nearest_x_idxs.min(), nearest_x_idxs.max() + 1),
            y_dim: slice(nearest_y_idxs.min(), nearest_y_idxs.max() + 1),
        }
    ).copy()


def crop_time_dimension(
    ds: xr.Dataset,
    start_dt: datetime,
    end_dt: datetime,
    time_dim_name: Optional[str] = None,
) -> xr.Dataset:
    """Crops the time dimension to the start and end datetimes."""
    if time_dim_name is None:
        time_dim_name = 'time'
    return ds.sel(
        {time_dim_name: slice(start_dt, end_dt)},
    ).copy(deep=True)
