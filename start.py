import os
from PIL import Image
from datetime import datetime

# 输出预设
success = '\033[0;32m[+]\033[0m'
error = '\033[0;31m[x]\033[0m' 
warning = '\033[0;33m[!]\033[0m'
done = '\033[0;36m[>]\033[0m'
separator = '\n================================\n'

def log_message(message_type, message):
    """将消息记录到日志文件中。"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('log.txt', 'a') as log_file:
        log_file.write(f"{timestamp} | {message_type} : {message}\n")

def openfile(file_path):
    with open(file_path, 'rb') as file:
        content = file.read()
    return content

def find_data_blocks(content, start_hex, end_hex, offset=0, ispack=0):
    """查找并提取两个十六进制字符串之间的数据块，可以指定额外的偏移量。"""
    start_bytes, end_bytes = bytes.fromhex(start_hex), bytes.fromhex(end_hex)
    start_index = content.find(start_bytes)
    end_index = content.find(end_bytes, start_index) if start_index != -1 else len(content)
    if ispack:
        return content[start_index + len(start_bytes) + offset:end_index] if end_index != -1 else None
    else:
        return content[start_index + len(start_bytes) + offset:end_index] if end_index != -1 else content[start_index + len(start_bytes) + offset:]

def split_into_chunks(data, offset, chunk_size):
    """将数据分割成指定大小的块。"""
    data = data[offset:]
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size) if i + chunk_size <= len(data)]

def parse_chunk(chunk):
    """解析数据块，提取文件名特征、坐标和尺寸。"""
    file_name_feature = ' '.join(f'{b:02X}' for b in chunk[:10])
    coordinates = tuple(int.from_bytes(chunk[i:i+3], 'big') for i in range(12, 20, 4))
    size = tuple(int.from_bytes(chunk[i:i+3], 'big') for i in range(20, 28, 4))
    return {'file_name_feature': file_name_feature, 'coordinates': coordinates, 'size': size}

def extract_filename(feature_hex, content):
    """根据特征十六进制字符串在内容中查找文件名。"""
    return find_data_blocks(content, feature_hex, '2710', 4)

def ensure_unique_filename(filename, directory):
    """确保文件名在指定目录中是唯一的。"""
    filename = os.path.join(directory, filename)
    count = 0
    name, extension = os.path.splitext(filename)
    while os.path.exists(f"{name}({count}){extension}"):
        count += 1
    return f"{name}({count}){extension}" if os.path.exists(filename) else filename

def crop_and_save_image(file_name, coordinates, size, texture_path, unpack_directory):
    """裁剪并保存图像。"""
    with Image.open(texture_path) as texture_image:
        right, lower = coordinates[0] + size[0], coordinates[1] + size[1]
        if right <= texture_image.width and lower <= texture_image.height:
            cropped_image = texture_image.crop((*coordinates, right, lower))
            if not os.path.exists(unpack_directory):
                os.makedirs(unpack_directory)
            new_filename = ensure_unique_filename(file_name, unpack_directory)
            cropped_image.save(new_filename)
            print(f"{success} 成功保存：{new_filename}")
        else:
            print(f"{error} 错误：裁剪区域超出了原始图像边界。坐标: {coordinates}, 尺寸: {size}")

def process_file(file_path, texture_path, output_directory):
    file_data = openfile(file_path)
    pack_section = find_data_blocks(file_data, '255041434B5F53454354494F4E25', '0000000200', 14, 1)
    if pack_section is None:
        log_message(error, f"未找到PACK_SECTION数据块。文件：{os.path.basename(file_path)}")
        return

    pose_section = find_data_blocks(file_data, '25504F53455F53454354494F4E25', '255054434C5F53454354494F4E25', 0)
    if pose_section is None:
        log_message(error, f"未找到POSE_SECTION数据块。文件：{os.path.basename(file_path)}")
        return
    
    if pack_section:
        chunks = split_into_chunks(pack_section, 2, 28)
        for chunk in chunks:
            parsed_chunk = parse_chunk(chunk)
            file_name = extract_filename(parsed_chunk['file_name_feature'], pose_section)
            if file_name:
                try:
                    file_name_str = file_name.decode('ascii') + '.png'
                    crop_and_save_image(file_name_str, parsed_chunk['coordinates'], parsed_chunk['size'], texture_path, output_directory)
                except UnicodeDecodeError as e:
                    log_message(error, f"文件名解码错误: {str(e)}. 源文件：{os.path.basename(file_path)}")
            else:
                log_message(warning, f"未找到文件名。源文件：{os.path.basename(file_path)}")

# 主程序
files_directory = 'files'
unpack_directory = 'unpack'
binary_files = [f for f in os.listdir(files_directory) if f.endswith('.pxls.bytes')]

for binary_file in binary_files:
    file_path = os.path.join(files_directory, binary_file)
    texture_path = file_path + '.texture_0.png'
    output_subdirectory = os.path.join(unpack_directory, binary_file.replace('.pxls.bytes', ''))
    
    try:
        print(f"{done} 正在处理文件：{binary_file}")
        process_file(file_path, texture_path, output_subdirectory)
        print(f"{done} 文件处理完成。{separator}")
    except Exception as e:
        log_message(error, f"处理文件 {binary_file} 时发生错误: {str(e)}")
        print(f"{error} 处理文件 {binary_file} 时发生错误，请查看log.txt文件获取详细信息。")

print(f"{done} 所有文件处理完成。")