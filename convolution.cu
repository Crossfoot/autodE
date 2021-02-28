#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define HEIGHT 333

/* Pseudocode for convolution given a 3D array (x, y, pixel) (to be done not on GPU since I don't know how to allocate and copy 2D memory yet)
convolution(baseArray, filter, targetArr)  
  direction = [[-1, -1], [-1, 0], [-1, 1]
               [0, -1], [0, 0], [0, 1]
               [1, -1], [1, 0], [1, 1]]
  for i from [1, 334]: # iterate across rows
    for j from [1, 501]: # each pixel in each row
      pixel = [0, 0, 0]
      for k from [0, 8]: # Filter iterating
        for l from [0, 2]:  # RGB in each pixel
          pixel[l] += baseArray[i + direction[k][0]][j + direction[k][1]][l] * filter[k]



*/

__global__ void convolution(int **a, float *b, int **c) {
  int idx = blockIdx.x * blockDim.x + threadIdx.x;
  /* This function is going to be designed with 0 padding in mind */
  float pixel[] = {0, 0, 0};
  int direction[] = {-HEIGHT - 1, -HEIGHT, -HEIGHT + 1, 
                        -1,          0,         1,
                       HEIGHT - 1, HEIGHT, HEIGHT + 1};
  for (int i = 0; i < 9; i++) {
    for (int j = 0; j < 3; j++) {
      int target_idx = idx + direction[i];
      if (target_idx )
      pixel[j] += a[idx + direction[i]][j] * b[i]; /* this is best case scenario, no out of bounds */
    }
  }
  int intPixel[3];
  /*for (int i = 0; i < 3; i++) {
    intPixel[i] = (int)pixel[i];
    printf("%d ", intPixel[i]);
  }
  printf("\n");*/
  c[idx] = intPixel;
}

/* Pseudocode for readPPM 

  Open file for reading
  read the first 3 lines, (color type, picture size [500x333], and how many colors are supported [255])
  store the picture size in an array [500, 333]
  store empty line [[0, 0, 0] ... [0, 0, 0]]
  For i to 333:
    push [0, 0, 0]
    for j to 500:
      push pixel
    push [0, 0, 0]
  push empty line [[0, 0, 0] ... [0, 0, 0]]
  return array of pixels with 0 padding

*/

int **readPPM(char *filename) {
  FILE *file = fopen(filename, "r");
  char *buffer = (char *)malloc(sizeof(char) * 2048), *token;
  size_t size = 2048;
  int xy[2], i = 0, j, **ppmArr, *pixel;
  /* process first 3 lines (color type, pic size, RGB size) */
  getline(&buffer, &size, file); /* p3 */ 
  getline(&buffer, &size, file); /* size */
  token = strtok(buffer, " ");
  do {
    xy[i++] = atoi(token);
  } while (token = strtok(NULL, " "));
  ppmArr = (int**)malloc(sizeof(int*) * xy[0] * xy[1]);
  getline(&buffer, &size, file);
  i = 0;
  while (getline(&buffer, &size, file) > 0) {
    pixel = (int*)malloc(sizeof(int) * 3);  
    pixel[0] = atoi(strtok(buffer, " "));
    for (j=1; j < 3; j++) {
      pixel[j] = atoi(strtok(NULL, " "));
    }
    ppmArr[i] = pixel;
    i++;
  }
  fclose(file);
  return ppmArr; 
}

void readPPMArr(int **ppmarr) {
  for (int i = 0; i < 500 * 333; i++) {
    printf("[");
    for (int k = 0; k < 3; k++) {
      printf("%d, ", ppmarr[i][k]);
    }
    printf("]\n");
  }
}

int main(int argc, char *argv[]) {
  int **ga, **gc, **ppm, **result=NULL;
  float *gb;
  float filter[] = {0, 0, 0,
                  0, 0, 1,
                  0, 0, 0};
  ppm = readPPM(argv[1]);
  printf("sizeof ppm = %d\n", ppm[0][0]);
  /* readPPMArr(ppm); */
  /* PPM read correctly */
  /* Remember, cudaMALLOC needs a pointer to give the memory address to */
  cudaMalloc((void ***) &ga, sizeof(int) * 500 * 333); /* input */
  cudaMalloc((void **) &gb, sizeof(float) * 3 * 3); /* filter */
  cudaMalloc((void ***) &gc, sizeof(int) * 500 * 333); /* output */
  cudaMemcpy(ga, ppm, sizeof(int) * 500 * 333, cudaMemcpyHostToDevice);
  cudaMemcpy(gb, filter, sizeof(float) * 3 * 3, cudaMemcpyHostToDevice);
  convolution<<<500,333>>>(ga,gb,gc);
  cudaMemcpy(result, gc, sizeof(int) * 500 * 333, cudaMemcpyDeviceToHost);
  printf("To here\n");
  readPPMArr(result);
  cudaFree(ga);
  cudaFree(gb);
  cudaFree(gc);
  return 0;
}
