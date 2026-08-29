#include <stdio.h>
#include <stdlib.h>
#include "mathx.h"
int main(int argc,char**argv){
  if(argc!=3) return 2;
  int a=atoi(argv[1]), b=atoi(argv[2]);
  printf("sum=%d product=%d\n", add(a,b), mul(a,b));
  return 0;
}
