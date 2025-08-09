from typing import List

def zero_striping(matrix: List[List[int]]) -> None:
# Use a flag to indicate if the first row initially contains any zero.
#
# Use a flag to indicate if the first column initially contains any zero.
#
# Traverse the submatrix, setting zeros in the first row and column to serve as markers for rows and columns that contain zeros.
#
# Apply zeros based on markers: iterate through the submatrix that starts from the second row and second column. For each cell, check if its corresponding marker in the first row or column is marked with a zero. If so, set that element to zero.
#
# If the first row was initially marked as containing a zero, set all elements in the first row to zero.
#
# If the first column was initially marked as having a zero, set all elements in the first column to zero.
    m, n = len(matrix), len(matrix[0])
    zero_rows, zero_cols = set(), set()
    for i in range(m):
        for j in range(n):
            if matrix[i][j] == 0:
                zero_rows.add(i)
                zero_cols.add(j)

    print(f"After marking: {matrix}")

    for i in range(m):
        for j in range(n):
            if i in zero_rows or j in zero_cols:
                matrix[i][j] = 0

matrix = [
    [1, 2, 3],
    [4, 0, 6],
    [7, 8, 9],
]
print(f"Input matrix: {matrix}")
zero_striping(matrix)
print(matrix)


matrix = [
    [1, 0, 3],
    [4, 5, 6],
    [7, 8, 9],
]
print(f"Input matrix: {matrix}")
zero_striping(matrix)
print(matrix)
