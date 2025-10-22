/*
 * ESP32 MPU6050 - 3D VISUALIZATION SENDER
 *
 * This code uses the MPU6050's internal DMP (Digital Motion Processor)
 * to get stable yaw, pitch, and roll angles.
 *
 * It then prints them to the Serial port in a format
 * that a Python GUI can understand.
 *
 * Required Library: MPU6050_tockn (Install via Arduino Library Manager)
 */

#include <Wire.h>
#include <MPU6050_tockn.h>

MPU6050 mpu(Wire);

// Use the default I2C pins (SDA=21, SCL=22)
// Make sure AD0 is connected to GND for address 0x68

void setup() {
  Serial.begin(115200);
  Wire.begin();
  
  mpu.begin();
  
  Serial.println("Calibrating MPU6050... Do not move the sensor.");
  // This step is important! It finds the resting "zero" offsets
  mpu.calcGyroOffsets(true); 
  Serial.println("Calibration Done!");
}

void loop() {
  // This function updates all sensor data and DMP calculations
  mpu.update();

  /*
   * Get the angles.
   * getAngleX() -> Pitch (rotation around X-axis)
   * getAngleY() -> Roll (rotation around Y-axis)
   * getAngleZ() -> Yaw (rotation around Z-axis)
   */
  float pitch = mpu.getAngleX();
  float roll = mpu.getAngleY();
  float yaw = mpu.getAngleZ();

  /*
   * Print the data as a simple comma-separated string.
   * Example: "12.34,-45.67,0.12\n"
   * The '\n' (newline) at the end is crucial.
   */
  Serial.print(roll);  // We send Roll (Y-axis) first
  Serial.print(",");
  Serial.print(pitch); // Then Pitch (X-axis)
  Serial.print(",");
  Serial.println(yaw); // Then Yaw (Z-axis)

  // Send data 50 times per second (a 20ms delay)
  delay(20); 
}
