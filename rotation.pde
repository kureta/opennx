import oscP5.*;
import netP5.*;

OscP5   osc;
float[] quat = {1,0,0,0};   // w, x, y, z

void setup() {
  size(600,600, P3D);
  noStroke();
  lights();
  // listen on UDP port 9000
  osc = new OscP5(this, 9000);
}

void draw() {
  background(30);
  // build rotation matrix from quaternion
  float w = -quat[3], x = quat[0], y = -quat[2], z = -quat[1];
  float xx = x*x, yy = y*y, zz = z*z;
  float xy = x*y, xz = x*z, yz = y*z;
  float wx = w*x, wy = w*y, wz = w*z;

  float m00 = 1 - 2*(yy + zz);
  float m01 =     2*(xy - wz);
  float m02 =     2*(xz + wy);

  float m10 =     2*(xy + wz);
  float m11 = 1 - 2*(xx + zz);
  float m12 =     2*(yz - wx);

  float m20 =     2*(xz - wy);
  float m21 =     2*(yz + wx);
  float m22 = 1 - 2*(xx + yy);

  // center and apply quaternion rotation
  translate(width/2, height/2, 0);
  applyMatrix(
    m00, m01, m02, 0,
    m10, m11, m12, 0,
    m20, m21, m22, 0,
      0,   0,   0, 1
  );

  // draw a cube
  fill(160,200,240);
  box(200);
}

// OSC callback: receives /quat w,x,y,z
void oscEvent(OscMessage msg) {
  if (msg.checkAddrPattern("/quat")) {
    // assume exactly 4 float arguments
    for (int i=0; i<4; i++) {
      quat[i] = msg.get(i).floatValue();
    }
  }
}
