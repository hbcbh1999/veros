from ... import veros_method
from .. import cyclic
from . import island, utilities, solve_poisson

@veros_method
def streamfunction_init(veros):
    """
    prepare for island integrals
    """
    maxipp = 10000
    mnisle = 1000
    allmap = np.zeros((veros.nx+4, veros.ny+4))
    boundary_map = np.zeros((veros.nx+4, veros.ny+4))
    forc = np.zeros((veros.nx+4, veros.ny+4))
    iperm = np.zeros(maxipp)
    jperm = np.zeros(maxipp)
    nippts = np.zeros(mnisle, dtype=np.int)
    iofs = np.zeros(mnisle, dtype=np.int)

    if veros.backend_name == "bohrium":
        boundary_map = boundary_map.copy2numpy()
        allmap = allmap.copy2numpy()
        iperm = iperm.copy2numpy()
        jperm = jperm.copy2numpy()
        nippts = nippts.copy2numpy()
        iofs = iofs.copy2numpy()

    print("Initializing streamfunction method")
    verbose = veros.enable_congrad_verbose
    """
    communicate kbot to get the entire land map
    """
    kmt = np.zeros((veros.nx+4, veros.ny+4)) # note that routine will modify kmt
    kmt[2:-2, 2:-2] = (veros.kbot[2:-2, 2:-2] > 0) * 5

    if veros.enable_cyclic_x:
        cyclic.setcyclic_x(kmt)

    """
    preprocess land map using MOMs algorithm for B-grid to determine number of islands
    """
    print(" starting MOMs algorithm for B-grid to determine number of islands")
    island.isleperim(veros, kmt, allmap, iperm, jperm, iofs, nippts, veros.nx+4, veros.ny+4, mnisle, maxipp, change_nisle=True, verbose=True)
    if veros.enable_cyclic_x:
        cyclic.setcyclic_x(allmap)
    _showmap(veros, allmap)

    """
    allocate variables
    """
    veros.boundary_mask = np.zeros((veros.nx+4, veros.ny+4, veros.nisle)).astype(np.bool)
    veros.line_dir_south_mask = np.zeros((veros.nx+4, veros.ny+4, veros.nisle)).astype(np.bool)
    veros.line_dir_north_mask = np.zeros((veros.nx+4, veros.ny+4, veros.nisle)).astype(np.bool)
    veros.line_dir_east_mask = np.zeros((veros.nx+4, veros.ny+4, veros.nisle)).astype(np.bool)
    veros.line_dir_west_mask = np.zeros((veros.nx+4, veros.ny+4, veros.nisle)).astype(np.bool)
    veros.psin = np.zeros((veros.nx+4, veros.ny+4, veros.nisle))
    veros.dpsin = np.zeros((veros.nisle, 3))
    veros.line_psin = np.zeros((veros.nisle, veros.nisle))

    if veros.backend_name == "bohrium":
        veros.boundary_mask = veros.boundary_mask.copy2numpy()
        veros.line_dir_south_mask = veros.line_dir_south_mask.copy2numpy()
        veros.line_dir_north_mask = veros.line_dir_north_mask.copy2numpy()
        veros.line_dir_east_mask  = veros.line_dir_east_mask.copy2numpy()
        veros.line_dir_west_mask  = veros.line_dir_west_mask.copy2numpy()

    for isle in xrange(veros.nisle): #isle=1,nisle
        print(" ------------------------")
        print(" processing island #{:d}".format(isle))
        print(" ------------------------")

        """
        land map for island number isle: 1 is land, -1 is perimeter, 0 is ocean
        """
        kmt[...] = allmap != isle+1
        island.isleperim(veros, kmt, boundary_map, iperm, jperm, iofs, nippts, veros.nx+4, veros.ny+4, mnisle, maxipp)
        if verbose:
            _showmap(veros, boundary_map)

        """
        find a starting point
        """
        n = 0
        # avoid starting close to cyclic bondaries
        (cont, ij, Dir, startPos) = _avoid_cyclic_boundaries(veros, boundary_map, isle, n, (veros.nx/2+1, veros.nx+2))
        if not cont:
            (cont, ij, Dir, startPos) = _avoid_cyclic_boundaries(veros, boundary_map, isle, n, (veros.nx/2,-1,-1))
            if not cont:
                raise RuntimeError("found no starting point for line integral")

        print(" starting point of line integral is {!r}".format(startPos))
        print(" starting direction is {!r}".format(Dir))

        """
        now find connecting lines
        """
        n = 1
        veros.boundary_mask[ij[0],ij[1], isle] = 1
        cont = True
        while cont:
            """
            consider map in front of line direction and to the right and decide where to go
            """
            if Dir[0]== 0 and Dir[1]== 1: # north
                ijp      = [ij[0]  ,ij[1]+1]
                ijp_right= [ij[0]+1,ij[1]+1]
            elif Dir[0]==-1 and Dir[1]== 0: # west
                ijp      = [ij[0]  ,ij[1]  ]
                ijp_right= [ij[0]  ,ij[1]+1]
            elif Dir[0]== 0 and Dir[1]==-1: # south
                ijp      = [ij[0]+1,ij[1]  ]
                ijp_right= [ij[0]  ,ij[1]  ]
            elif Dir[0]== 1 and Dir[1]== 0: # east
                ijp      = [ij[0]+1,ij[1]+1]
                ijp_right= [ij[0]+1,ij[1]  ]

            """
            4 cases are possible
            """

            if verbose:
                print(" ")
                print(" position is {!r}".format(ij))
                print(" direction is {!r}".format(Dir))
                print(" map ahead is {} {}".format(boundary_map[ijp[0],ijp[1]], boundary_map[ijp_right[0],ijp_right[1]]))

            if boundary_map[ijp[0],ijp[1]] == -1 and boundary_map[ijp_right[0],ijp_right[1]] == 1:
                if verbose:
                    print(" go forward")
            elif boundary_map[ijp[0],ijp[1]] == -1 and boundary_map[ijp_right[0],ijp_right[1]] == -1:
                if verbose:
                    print(" turn right")
                Dir = [Dir[1],-Dir[0]]
            elif boundary_map[ijp[0],ijp[1]] == 1 and boundary_map[ijp_right[0],ijp_right[1]] == 1:
                if verbose:
                    print(" turn left")
                Dir = [-Dir[1],Dir[0]]
            elif boundary_map[ijp[0],ijp[1]] == 1 and boundary_map[ijp_right[0],ijp_right[1]] == -1:
                if verbose:
                    print(" turn left")
                Dir = [-Dir[1],Dir[0]]
            else:
                print(" map ahead is {} {}".format(boundary_map[ijp[0],ijp[1]], boundary_map[ijp_right[0],ijp_right[1]]))
                raise RuntimeError("unknown situation or lost track")

            """
            go forward in direction
            """
            if Dir[0]== 0 and Dir[1]== 1: #north
                veros.line_dir_north_mask[ij[0], ij[1], isle] = 1
            elif Dir[0]==-1 and Dir[1]== 0: #west
                veros.line_dir_west_mask[ij[0], ij[1], isle] = 1
            elif Dir[0]== 0 and Dir[1]==-1: #south
                veros.line_dir_south_mask[ij[0], ij[1], isle] = 1
            elif Dir[0]== 1 and Dir[1]== 0: #east
                veros.line_dir_east_mask[ij[0], ij[1], isle] = 1
            ij = [ij[0] + Dir[0], ij[1] + Dir[1]]
            if startPos[0] == ij[0] and startPos[1] == ij[1]:
                cont = False

            """
            account for cyclic boundary conditions
            """
            if veros.enable_cyclic_x and Dir[0] == 1 and Dir[1] == 0 and ij[0] > veros.nx+1:
                if verbose:
                    print(" shifting to western cyclic boundary")
                ij[0] -= veros.nx
            if veros.enable_cyclic_x and Dir[0] == -1 and Dir[1] == 0 and ij[0] < 2:
                if verbose:
                    print(" shifting to eastern cyclic boundary")
                ij[0] += veros.nx
            if startPos[0] == ij[0] and startPos[1] == ij[1]:
                cont = False

            if cont:
                n += 1
                veros.boundary_mask[ij[0],ij[1],isle] = 1

        print(" number of points is {:d}".format(n+1))
        if verbose:
            print(" ")
            print(" Positions:")
            print(" boundary: {!r}".format(veros.boundary_mask[...,isle]))

    if veros.backend_name == "bohrium":
        veros.boundary_mask = np.asarray(veros.boundary_mask)
        veros.line_dir_south_mask = np.asarray(veros.line_dir_south_mask)
        veros.line_dir_north_mask = np.asarray(veros.line_dir_north_mask)
        veros.line_dir_east_mask  = np.asarray(veros.line_dir_east_mask)
        veros.line_dir_west_mask  = np.asarray(veros.line_dir_west_mask)

    """
    precalculate time independent boundary components of streamfunction
    """
    forc[...] = 0.0
    # initialize with noise to achieve uniform convergence
    veros.psin[...] = np.random.rand(*veros.psin.shape)

    for isle in xrange(veros.nisle):
        print(" solving for boundary contribution by island {:d}".format(isle))
        solve_poisson.solve(veros, forc, veros.psin[:,:,isle], boundary_val=veros.boundary_mask[:,:,isle])

    if veros.enable_cyclic_x:
        cyclic.setcyclic_x(veros.psin)

    """
    precalculate time independent island integrals
    """
    fpx = np.zeros((veros.nx+4, veros.ny+4, veros.nisle))
    fpy = np.zeros((veros.nx+4, veros.ny+4, veros.nisle))

    fpx[1:, 1:, :] = -veros.maskU[1:, 1:, -1, np.newaxis] \
            * (veros.psin[1:, 1:, :] - veros.psin[1:, :-1, :]) \
            / veros.dyt[np.newaxis,1:,np.newaxis] * veros.hur[1:, 1:, np.newaxis]
    fpy[1:, 1:, ...] = veros.maskV[1:, 1:, -1, np.newaxis] \
            * (veros.psin[1:, 1:, :] - veros.psin[:-1, 1:, :]) \
            / (veros.cosu[np.newaxis,1:,np.newaxis] * veros.dxt[1:, np.newaxis, np.newaxis]) \
            * veros.hvr[1:, 1:, np.newaxis]
    veros.line_psin[...] = utilities.line_integrals(veros, fpx, fpy, kind="full")

@veros_method
def _avoid_cyclic_boundaries(veros, boundary_map, isle, n, x_range):
    for i in xrange(*x_range):
        for j in xrange(1, veros.ny+2):
            if boundary_map[i,j] == 1 and boundary_map[i,j+1] == -1:
                #initial direction is eastward, we come from the west
                cont = True
                Dir = [1,0]
                veros.line_dir_east_mask[i-1, j, isle] = 1
                veros.boundary_mask[i-1, j, isle] = 1
                return cont, (i,j), Dir, (i-1, j)
            if boundary_map[i,j] == -1 and boundary_map[i,j+1] == 1:
                # initial direction is westward, we come from the east
                cont = True
                Dir = [-1,0]
                veros.line_dir_west_mask[i, j, isle] = 1
                veros.boundary_mask[i, j, isle] = 1
                return cont, (i-1,j), Dir, (i,j)
    return False, None, [0,0], [0,0]

@veros_method
def _showmap(veros, boundary_map):
    linewidth = 125
    imt = veros.nx + 4
    iremain = imt
    istart = 0
    print("")
    print(" "*(5+min(linewidth,imt)/2-13) + "Land mass and perimeter")
    for isweep in xrange(1, imt/linewidth + 2):
        iline = min(iremain, linewidth)
        iremain = iremain - iline
        if iline > 0:
            print(" ")
            print("".join(["{:5d}".format(istart+i+1-2) for i in xrange(1,iline+1,5)]))
            for j in xrange(veros.ny+3, -1, -1):
                print("{:3d} ".format(j) + "".join([str(int(_mod10(boundary_map[istart+i -2,j]))) if _mod10(boundary_map[istart+i -2,j]) >= 0 else "*" for i in xrange(2, iline+2)]))
            print("".join(["{:5d}".format(istart+i+1-2) for i in xrange(1,iline+1,5)]))
            istart = istart + iline
    print("")

def _mod10(m):
    if m > 0:
        return m % 10
    else:
        return m