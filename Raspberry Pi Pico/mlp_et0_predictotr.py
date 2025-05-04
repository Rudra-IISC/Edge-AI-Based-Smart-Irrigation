# MicroPython script for MLP Regressor inference on Raspberry Pi Pico
# Target: Predict ET0 based on T2M_MAX, RH2M, ALLSKY_SFC_SW_DWN

import math
import time

# --- !!! PASTE PARAMETERS HERE !!! ---
# Paste the output from the Python extraction script below
# --- Scaler Parameters ---
SCALER_MEAN = [30.523708026575687, 67.71459507990662, 18.924402944873407]
SCALER_SCALE = [3.5751311909811117, 15.723214825593704, 48.63370888697871]

# --- MLP Parameters ---
# Weights: Layer 0 (Input/Previous Layer -> Layer 1)
WEIGHTS_0 = [
    [0.053256736082930384, 0.4556614644198747, 0.2956831098132046, 0.390611203857762, -0.49573082787825595, -0.26712442338928777, -0.4410235572435593, 0.3151124934653342, -2.0374896975933982e-147, -6.093239597537111e-106, -0.20590779631744852, 0.7770397050391823, 0.3815640516921651, -0.7107079169172609, -0.002707618226200019, 0.09307386063733245],
    [-0.16791817815558072, 0.08396617595601202, 0.04362431244958579, -0.42207432737964884, 0.4441163443582557, -0.48997516700048205, 0.3513257685067875, -0.004191927572604342, -1.239003522970632e-174, -1.4862611111652933e-84, 0.6979751005863711, -0.13542948790788364, -0.0042729855928596155, -0.23871321463091302, -0.02134113163304481, -0.5223530333312946],
    [-1.4340603348132237, -0.05623138321566759, 1.7802483055245486, 1.304945190351235, 0.9776157424983497, 0.3139871734563571, 0.6882998578682952, 0.7509840348275748, -1.6051166764073653e-63, -1.1210733326638123e-185, -1.7166667434170877, 1.2848190660888648, -1.1185322851024773, 0.060356849975963626, 1.2126690761625336, 1.0232338882640604],
]

# Weights: Layer 1 (Input/Previous Layer -> Layer 2)
WEIGHTS_1 = [
    [-0.2847830853942866, -0.04894336945156456, 1.4583131433425092, 1.5143253850143812e-88, -0.7264039088864096, 0.42587725204011, 0.11949961610694788, -0.36591673142405284],
    [-0.2728998340358246, 0.24023646185119688, 0.20597304427292465, 8.446412413067904e-108, 0.5784438720016305, -0.46510428666278403, -0.2148554543803399, -0.16401721895707813],
    [0.7254694744452723, 0.04824566701970705, -0.173761248281168, 6.272802759676992e-62, 0.27607020056716475, -0.23090869429103414, 0.018611815288953167, 0.49879112742900256],
    [0.7285477397563662, -0.11779578123363092, -0.30222207999295625, -1.7846750911207596e-112, 0.6570346079299098, 0.008007215865847352, 0.08755759404773678, 0.33411984891123125],
    [0.38566036718287616, -0.11015269727783522, -0.48726546431718504, -7.538667466497139e-70, 0.04892677014818802, 0.08756335073999622, -0.43456544962087124, 0.37059220426233663],
    [0.7148494488495825, -0.3706853387737396, -0.03162654699387281, -4.968561076246304e-100, 0.13579624047710168, -0.4750581572187915, -0.4092720315250236, -0.03229553741430834],
    [0.8141288665073991, 0.29615426316505034, 0.17812947377421573, 3.652025208159293e-74, 0.7728911644083547, -0.32875867990806895, 0.03664436727722565, 0.4227755184441739],
    [0.6159664563699541, 0.321362806693978, 0.0037792297391362364, -6.357920888698645e-70, 0.1434289041190022, -0.1258979069632879, 0.15496368113763198, 0.6679399768785638],
    [-3.624311282752862e-52, -9.734464534961656e-185, 1.2227100458183595e-160, 3.6768523804866795e-95, 6.254653188883465e-72, 2.3453651086205982e-129, 3.1130640866873725e-60, 1.5318229952195728e-123],
    [2.5065569859141277e-183, -4.736891421768007e-115, 2.5873796880493072e-138, -1.352226087584374e-55, 6.539773669408313e-57, 5.221895600786153e-102, 5.75951463657817e-186, -1.4956683598249917e-116],
    [-0.7018792326039285, -0.4566868649430578, -0.37596590389659923, -5.214925711343096e-186, -0.9691546031029429, 1.2066615381531683e-109, 1.0163128906141286, -0.7468579314889985],
    [0.0063916082016488626, -0.09838164764903408, 0.5512446426326887, -1.2147597931374713e-99, 0.5673896116942954, 0.19613574244491702, -0.4296771100893114, 0.5888254689718364],
    [-0.17109912955552728, 0.04836384267418337, 0.9328249649835226, -3.400976765060054e-179, -0.5248353305947155, 0.2778542717164251, -0.29509812468990027, -0.3519718611312421],
    [-0.5764362857485142, 0.0031381195131248833, -0.566643017773637, -7.490191247189335e-54, -0.14028206866182227, -0.28066032131588753, -0.20175338138508545, -0.44347037925567717],
    [0.5809873822504297, -0.14880527949533928, 0.0006068468133094703, -1.6157652203472783e-75, 0.3741559035340779, -0.4424730018969445, 0.16706676966043313, 0.766240728279984],
    [0.09518650821029383, 0.04455443646256285, 0.24434554403252773, -2.8504645051703925e-172, 0.3522879938885286, -0.10786214919336565, -0.6042224395835604, 0.7340580447695334],
]

# Weights: Layer 2 (Input/Previous Layer -> Layer 3)
WEIGHTS_2 = [
    [0.5664609979160748],
    [-0.6356844552555531],
    [-0.790921774976537],
    [1.0174909008196275e-29],
    [0.6648815872830408],
    [-0.7581555113582894],
    [-0.5808776834343329],
    [0.6389814925338703],
]

# Biases: Layer 1
BIASES_0 = [-0.0900813784109052, -0.32239141701777874, 0.9895977041668974, 0.6468650926165534, 0.8748347751862976, 0.6685067157960585, 0.508265633763575, 0.7579812511181253, -0.4624945007251862, -0.34168576504309, -0.4208648595662413, 0.22662123091992215, -0.054544680440006044, -0.2806397368438346, 0.8259691546186022, 0.12604276939324174]

# Biases: Layer 2
BIASES_1 = [0.6926480824329304, 0.053241274443864485, -0.18648836023061607, -0.1507904253873391, 0.6334437732214047, 0.3417859021747934, 0.2062404013732311, 0.5709789833548106]

# Biases: Layer 3
BIASES_2 = [-0.5699131677038413]



# --- Helper Functions ---

def scale_features(raw_features, means, scales):
    """Applies StandardScaler logic"""
    if len(raw_features) != len(means) or len(raw_features) != len(scales):
        raise ValueError("Feature length mismatch with scaler params")
    scaled = [0.0] * len(raw_features)
    for i in range(len(raw_features)):
        if scales[i] == 0: # Avoid division by zero
             scaled[i] = 0.0
        else:
            scaled[i] = (raw_features[i] - means[i]) / scales[i]
    return scaled

def relu(x):
    """ReLU activation function"""
    return max(0.0, x)

def identity(x):
    """Identity activation function (for output layer)"""
    return x

def dot_product(vector_a, vector_b):
    """Calculates the dot product of two vectors (lists)"""
    if len(vector_a) != len(vector_b):
        raise ValueError("Vector lengths must match for dot product")
    result = 0.0
    for i in range(len(vector_a)):
        result += vector_a[i] * vector_b[i]
    return result

def matrix_vector_multiply(matrix, vector):
    """Multiplies a matrix (list of lists) by a vector (list)"""
    if not matrix:
        return []
    if len(matrix[0]) != len(vector):
        # Check columns of matrix against vector length
        # Adjusting check for weights matrix format (rows are neurons, columns are inputs)
         transposed_cols = len(matrix)
         transposed_rows = len(matrix[0]) if matrix else 0
         if transposed_rows != len(vector):
              raise ValueError(f"Matrix columns ({transposed_rows}) must match vector length ({len(vector)})")

         # Perform multiplication assuming matrix rows = neurons, matrix cols = inputs
         result_vector = [0.0] * len(matrix) # Output size is number of neurons (rows)
         for i in range(len(matrix)): # Iterate through each neuron (row)
             neuron_weights = matrix[i]
             if len(neuron_weights) != len(vector):
                 raise ValueError(f"Neuron weights length ({len(neuron_weights)}) mismatch with input vector ({len(vector)}) at neuron {i}")
             result_vector[i] = dot_product(neuron_weights, vector)
         return result_vector


    # Original check (assuming matrix rows = features, matrix columns = neurons) - less common for NN weights layout
    # if len(matrix[0]) != len(vector):
    #      raise ValueError("Matrix columns must match vector length")
    # result_vector = [0.0] * len(matrix) # Output length is number of rows
    # for i in range(len(matrix)):
    #     result_vector[i] = dot_product(matrix[i], vector)
    # return result_vector# --- Place this corrected function in your mlp_model.py file ---

def predict_et0(raw_features):
    """
    Predicts ET0 using the hardcoded MLP parameters.
    Args:
        raw_features (list): A list containing [T2M_MAX, RH2M, ALLSKY_SFC_SW_DWN]
                             in their original scale.
    Returns:
        float: The predicted ET0 value.
    """
    if len(raw_features) != len(SCALER_MEAN):
         raise ValueError(f"Expected {len(SCALER_MEAN)} features, got {len(raw_features)}")

    # 1. Scale the input features
    scaled_input = scale_features(raw_features, SCALER_MEAN, SCALER_SCALE)

    # --- Manual Feedforward Calculation ---

    # Hidden Layer 1 Calculation (Input -> Layer 1)
    layer1_neurons = len(BIASES_0) # Should be 16 based on your BIASES_0
    layer1_output = [0.0] * layer1_neurons
    for i in range(layer1_neurons): # For each neuron in layer 1
        # Get weights for this neuron: column i from WEIGHTS_0
        neuron_input_weights = [WEIGHTS_0[j][i] for j in range(len(scaled_input))]
        activation = dot_product(scaled_input, neuron_input_weights) + BIASES_0[i]
        layer1_output[i] = relu(activation) # Apply ReLU

    # Hidden Layer 2 Calculation (Layer 1 -> Layer 2)
    layer2_neurons = len(BIASES_1) # Should be 8 based on your BIASES_1
    layer2_output = [0.0] * layer2_neurons
    for i in range(layer2_neurons): # For each neuron in layer 2
        # Get weights for this neuron: column i from WEIGHTS_1
        neuron_input_weights = [WEIGHTS_1[j][i] for j in range(len(layer1_output))]
        activation = dot_product(layer1_output, neuron_input_weights) + BIASES_1[i]
        layer2_output[i] = relu(activation) # Apply ReLU (Typical for hidden layers)

    # Output Layer 3 Calculation (Layer 2 -> Output)
    layer3_neurons = len(BIASES_2) # Should be 1 based on your BIASES_2
    output_value = [0.0] * layer3_neurons
    for i in range(layer3_neurons): # For each neuron in output layer
        # Get weights for this neuron: column i from WEIGHTS_2
        neuron_input_weights = [WEIGHTS_2[j][i] for j in range(len(layer2_output))]
        activation = dot_product(layer2_output, neuron_input_weights) + BIASES_2[i]
        output_value[i] = identity(activation) # Apply Identity for regression output

    # Final output is the result from the last layer
    if len(output_value) != 1:
        print("Warning: MLP model expected a single output neuron for regression.")
        # Handle multiple outputs if necessary, e.g., return the list or average
        # Returning the first element assuming single output was intended.
        return output_value[0]

    return output_value[0]

# --- Keep the rest of your mlp_model.py file (imports, params, helpers) as is ---
# --- Remove or comment out the if __name__ == "__main__": block if saving as a module ---
# if __name__ == "__main__":
#     # ... example usage ...Example Usage ---
if __name__ == "__main__":
    # Example input features (Replace with actual sensor readings)
    # Format: [T2M_MAX, RH2M, ALLSKY_SFC_SW_DWN]
    example_input = [30.5, 55.2, 250.7] # Example values

    print(f"Input Features: {example_input}")

    start_time = time.ticks_us() # Measure prediction time

    try:
        predicted_value = predict_et0(example_input)
        print(f"Predicted ET0: {predicted_value}")
    except ValueError as e:
        print(f"Error during prediction: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


    end_time = time.ticks_us()
    duration_ms = time.ticks_diff(end_time, start_time) / 1000.0
    print(f"Prediction took: {duration_ms:.2f} ms")

    # Example with different values
    example_input_2 = [25.0, 70.0, 180.0]
    print(f"\nInput Features: {example_input_2}")
    try:
        predicted_value_2 = predict_et0(example_input_2)
        print(f"Predicted ET0: {predicted_value_2}")
    except ValueError as e:
        print(f"Error during prediction: {e}")

