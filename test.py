from ultralytics import YOLO
import cv2

# Load YOLO model
model = YOLO("yolo11n.pt")

# Open traffic video
video_path = "videos/traffic.mp4"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("ERROR: Could not open traffic video")
    exit()

# Get video dimensions
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"Video size: {width} x {height}")

# Create window
window_name = "SmartFlow - Vehicle Counting"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

display_width = 1200
display_height = int(display_width * height / width)

cv2.resizeWindow(window_name, display_width, display_height)


while True:

    ret, frame = cap.read()

    if not ret:
        print("Video finished.")
        break

    # Run YOLO
    results = model(frame, verbose=False)

    # Get detected objects
    boxes = results[0].boxes

    # Vehicle counters
    car_count = 0
    motorcycle_count = 0
    bus_count = 0
    truck_count = 0

    # Check every detected object
    for box in boxes:

        class_id = int(box.cls[0])

        # YOLO class IDs
        if class_id == 2:
            car_count += 1

        elif class_id == 3:
            motorcycle_count += 1

        elif class_id == 5:
            bus_count += 1

        elif class_id == 7:
            truck_count += 1

    # Total vehicles
    total_vehicles = (
        car_count
        + motorcycle_count
        + bus_count
        + truck_count
    )

    # Draw detection boxes
    annotated_frame = results[0].plot()

    # Display vehicle counts
    cv2.putText(
        annotated_frame,
        f"Cars: {car_count}",
        (30, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.putText(
        annotated_frame,
        f"Motorcycles: {motorcycle_count}",
        (30, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.putText(
        annotated_frame,
        f"Buses: {bus_count}",
        (30, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.putText(
        annotated_frame,
        f"Trucks: {truck_count}",
        (30, 160),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.putText(
        annotated_frame,
        f"TOTAL VEHICLES: {total_vehicles}",
        (30, 210),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (0, 0, 255),
        3
    )

    # Show video
    cv2.imshow(window_name, annotated_frame)

    # Press Q to exit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()