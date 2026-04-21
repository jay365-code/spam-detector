const clusterSizeMap = new Map();
clusterSizeMap.set(1, 10);
clusterSizeMap.set(2, 5);
clusterSizeMap.set(3, 20);

let arr = [
  {id: 1, c: 1}, {id: 2, c: 1}, {id: 3, c: 2}, {id: 4, c: 3}, {id: 5, c: 3}
];

arr.sort((a, b) => {
  const sizeA = clusterSizeMap.get(a.c);
  const sizeB = clusterSizeMap.get(b.c);
  if (sizeA !== sizeB) return sizeB - sizeA;
  return a.c - b.c;
});

console.log(arr.map(x => x.c));
