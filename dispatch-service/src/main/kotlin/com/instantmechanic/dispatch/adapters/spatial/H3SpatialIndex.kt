package com.instantmechanic.dispatch.adapters.spatial

import com.instantmechanic.dispatch.domain.port.SpatialIndex
import com.uber.h3core.H3Core

/** H3 Java binding adapter. Core never imports this class. */
class H3SpatialIndex : SpatialIndex {
    private val h3: H3Core = H3Core.newInstance()

    override fun cell(lat: Double, lon: Double, resolution: Int): String =
        h3.latLngToCellAddress(lat, lon, resolution)

    override fun parent(cell: String, resolution: Int): String =
        h3.cellToParentAddress(cell, resolution)

    override fun ring(cell: String, k: Int): Set<String> = h3.gridDisk(cell, k).toSet()
}
