"""Preprocessing functions.
"""

from typing import Tuple

import numpy as np
from tqdm import tqdm

from hexsample.fileio import DigiInputFileCircular
from hexsample.hexagon import HexagonalGrid, HexagonalLayout


def circular_crown_logical_coordinates(column: int, row: int, grid: HexagonalGrid)\
    -> Tuple[np.ndarray, np.ndarray]:
    """This function returns a set of 7 tuples (col, row) containing the logical
    coordinates of the pixels in a DigiCircularEvent in a standard ordering.
    Consider the following legend: 
    c = central, ur = up-right, r = right, dr = down-right, d = down, 
    dl = down-left, l = left, ul = upper-left.
    The output array has the tuples in the following order:
    [c, ur, r, dr, d, dl, l, ul]

    Arguments
    ---------
    column : int
        central pixel column in pixel logical coordinates;
    row : int
        central pixel row in pixel logical coordinates;
    grid : HexagonalGrid
        class containing the informations about the hexagonal grid features and
        the methods for localizing the neighbors of a given pixel.
    """
    coordinates = [(column, row)] + [(c, r) for c, r in grid.neighbors(column, row)]
    return coordinates

class Xraydata():
    """Class that preprocesses data from a .h5 file and creates the input arrays
    for the NN.
    """
    def __init__(self, file_path: str):
        """Class constructor

        Arguments
        ---------
        file_path : str
            String containing the path to the .h5 file to be processed.
        """
        # Initializing the DigiEventCircular from the .h5 input file
        self.input_file = DigiInputFileCircular(file_path)
        # Initializing the HexagonalGrid
        # Extrapolation of informations of the HexagonalGrid from the file header
        layout = self.input_file.root.header._v_attrs['layout']
        numcolumns = self.input_file.root.header._v_attrs['numcolumns']
        numrows = self.input_file.root.header._v_attrs['numrows']
        pitch = self.input_file.root.header._v_attrs['pitch']
        # Construction of the HexagonalGrid. This is needed because the coordinates
        # of the adjacent pixels of a given one depends on the layout.
        self.grid = HexagonalGrid(HexagonalLayout(layout), numcolumns, numrows, pitch)

    def __del__(self):
        """Instance destructor. This is needed for the proper closing of the 
        input data file.
        """
        # Closing the input file ...
        self.input_file.close()
        # ... and then deleting the class instance. 
    
    def __repr__(self) -> str:
        """Printing the general informations about the simulation
        """
        group_path = '/header'
        group = self.input_file.get_node(group_path)
        for attr_name in group._v_attrs._f_list():
            print(f'{attr_name}: {group._v_attrs[attr_name]}')
        return ''

    def highest_pixel_coordinates(self) -> np.array:
        """This function returns a numpy array containing the physical coordinates
        of the highest pixel (the one that defines the position of the cluster). 
        This function is not useful for the NN intself, instead for performance 
        evaluation tasks.
        """
        # Creating lists for storing the x and y coordinates
        x = []
        y = []
        for evt in self.input_file:
            x_tmp, y_tmp = self.grid.pixel_to_world(evt.column, evt.row)
            x.append(x_tmp)
            y.append(y_tmp)
        return x, y
            
    def input_events_data(self) -> np.array:
        """This function returns a numpy array containing in every row the data 
        of a single event to be given as input to the neural network.
        Before stacking data inside an array, it is necessary to preprocess them.
        Central pixel position is converted from logical coordinates (col, row) to 
        cartesian coordinates (x_max, y_max), PHA array is rearranged in a standard ordering. 
        Consider the following legend: 
        ur = up-right, r = right, dr = down-right, 
        dl = down-left, l = left, ul = upper-left.
        The output array has the data in the following order:
        [central pha, ur pha, r pha, dr pha, dl pha, l pha, ul pha, central x, central y]
        """
        # Extrapolation of data from the DigiEventCircular events
        events_data = []
        # Looping on events: extrapolating data and converting into required format
        for i, event in tqdm(enumerate(self.input_file)):
            # Storing of pixel's logical coordinates...
            coordinates = circular_crown_logical_coordinates(event.column, event.row, self.grid)
            # ... conversion from logical to ADC coordinates for standardizing the order ...
            adc_channel_order = [self.grid.adc_channel(_col, _row) for _col, _row in coordinates]
            # ... storing the re-ordered PHA list ...
            pha = event.pha[adc_channel_order]
            # ... separating x and y from coordinates tuples ...
            x_logical, y_logical = zip(*coordinates)
            # ... and converting from logical to physical coordinates ...
            # (note that the function pixel_to_world() needs the conversion
            # from tuples to numpy array)
            x, y = self.grid.pixel_to_world(np.array(x_logical), np.array(y_logical))
            # ... then stack the coordinates with its corresponding signal value
            # and append the result to the data list.
            events_data.append(np.stack((list(zip(pha, x-x[0], y-y[0]))), axis=0))
        # Return the events_data list of arrays.
        return np.array(events_data)

    def target_data(self) -> np.array:
        """This function returns a numpy array containing the target quantities
        extracted by the MC truth of the events. 
        """
        #print(coords)
        # Extrapolation of informations from the MC columns
        energy_target_array = self.input_file.mc_column('energy')
        x_hit = self.input_file.mc_column('absx')
        y_hit = self.input_file.mc_column('absy')
        # Defining the target array containing the energies
        target_energy = np.array(energy_target_array)
        # Rescale of hit coordinates with respect to the coordinates of the
        # maximum signal pixel
        # Extrapolating columns, rows of event
        cols = np.array([event.column for event in self.input_file])
        rows = np.array([event.row for event in self.input_file])
        x_max, y_max = self.grid.pixel_to_world(cols, rows)
        # MC positions are re-scaled with respect to (x_max, y_max), then
        # zipped and stacked for obtaining the desired format [x, y] for
        # every column of the returned array.
        # The positions are taken as shift from the central pixel
        target_coordinates = np.stack((list(zip(x_hit-x_max, y_hit-y_max))), axis=0)
        target_array = np.stack((list(zip(energy_target_array, x_hit-x_max, y_hit-y_max))), axis=0)
        # The returned list contains the energies and the positions of every
        # simulated event.
        return target_array

    
    def close_input_file(self):
        ''' Method for closing the input file
        '''
        self.input_file.close()

if __name__ == "__main__":
    # Loading an hexsample simulation and storing its content into an Xraydata object
    # The following simulation is a simulation with no electronic noise.
    file_path = '/Users/chiara/hexsampledata/hxsim_20ENC.h5'
    # Creating an istance of the class Xraydata that contains the data preprocessing methods
    data = Xraydata(file_path)
    print(data)

    del data

