import os
import json
import re
from docx import Document

def parse_schedules():
    all_schedule = {}
    
    # Регулярное выражение для поиска ваших файлов
    file_pattern = re.compile(r"Расписание УП Группа № (\d+)\. Лето 2026\.docx")
    
    # Карта дней недели для дат практики на лето 2026 года
    days_map = {
        "29.06": "Понедельник", "30.06": "Вторник", "01.07": "Среда", "02.07": "Четверг", "03.07": "Пятница",
        "06.07": "Понедельник", "07.07": "Вторник", "08.07": "Среда", "09.07": "Четверг", "10.07": "Пятница",
        "13.07": "Понедельник", "14.07": "Вторник", "15.07": "Среда", "16.07": "Четверг", "17.07": "Пятница",
        "20.07": "Понедельник", "21.07": "Вторник", "22.07": "Среда", "23.07": "Четверг", "24.07": "Пятница"
    }

    # Ищем файлы в текущей директории
    for file_name in os.listdir("."):
        match = file_pattern.match(file_name)
        if not match:
            continue
            
        group_num = match.group(1)
        group_key = f"Группа {group_num}"
        all_schedule[group_key] = {}
        
        doc = Document(file_name)
        
        for table in doc.tables:
            if len(table.rows) < 2:
                continue
            
            # Извлекаем даты из второй строки (шапки таблицы)
            dates = []
            header_cells = table.rows[1].cells
            for cell in header_cells:
                text = cell.text.strip()
                # Ищем даты формата ДД.ММ или ДД.ММ.
                date_match = re.search(r"(\d{2}\.\d{2})", text)
                if date_match:
                    dates.append(date_match.group(1))
                else:
                    dates.append(None)
            
            # Идем по строкам с занятиями (начиная с 3-й строки)
            for row in table.rows[2:]:
                cells = [c.text.strip() for c in row.cells]
                if not cells or not cells[0]:
                    continue
                
                # Первая ячейка — это время (например, "830-1200")
                raw_time = cells[0].split("\n")[0].strip()
                # Форматируем время для красоты (например, 8:30 - 12:00)
                time_match = re.match(r"(\d{1,2})(\d{2})[-–](\d{1,2})(\d{2})", raw_time.replace(" ", ""))
                if time_match:
                    time_slot = f"{time_match.group(1)}:{time_match.group(2)} - {time_match.group(3)}:{time_match.group(4)}"
                else:
                    time_slot = raw_time
                
                # Сопоставляем данные колонок с датами
                for col_idx, date_str in enumerate(dates):
                    if not date_str or col_idx >= len(cells):
                        continue
                        
                    cell_content = cells[col_idx].strip()
                    # Игнорируем пустые ячейки и перерывы
                    if not cell_content or "Перерыв" in cell_content:
                        continue
                    
                    # Приводим дату к международному формату YYYY-MM-DD
                    day, month = date_str.split(".")
                    full_date = f"2026-{month}-{day}"
                    
                    if full_date not in all_schedule[group_key]:
                        all_schedule[group_key][full_date] = {
                            "day_of_week": days_map.get(date_str, "Будний день"),
                            "lessons": []
                        }
                    
                    # Интеллектуальное разделение содержимого ячейки
                    # Очищаем строки от лишних переносов
                    clean_content = clean_text(cell_content)
                    
                    # Попробуем выделить аудиторию
                    classroom = "Не указана"
                    classroom_match = re.search(r"(ауд\.\s*[\d,\s]+)", clean_content)
                    if classroom_match:
                        classroom = classroom_match.group(1).strip()
                        clean_content = clean_content.replace(classroom, "").strip()
                    
                    # Пытаемся разделить оставшийся текст на Предмет и Преподавателя
                    parts = [p.strip() for p in clean_content.split(",") if p.strip()]
                    if len(parts) >= 2:
                        subject = parts[0]
                        teacher = parts[1]
                    elif len(parts) == 1:
                        # Если разделения запятой нет, проверяем наличие инициалов Ф.О.
                        teacher_match = re.search(r"([А-Я][а-я]+\s+[А-Я]\.\s*[А-Я]\.)", parts[0])
                        if teacher_match:
                            teacher = teacher_match.group(1)
                            subject = parts[0].replace(teacher, "").strip()
                        else:
                            subject = parts[0]
                            teacher = "Не указан"
                    else:
                        subject = clean_content
                        teacher = "Не указан"
                    
                    # Убираем лишние висящие знаки препинания
                    subject = subject.strip(",- ")
                    teacher = teacher.strip(",- ")
                    
                    all_schedule[group_key][full_date]["lessons"].append({
                        "time": time_slot,
                        "subject": subject,
                        "teacher": teacher,
                        "classroom": classroom
                    })

    # Сохраняем результат в единый JSON файл
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(all_schedule, f, ensure_ascii=False, indent=2)
    print("Успешно! Расписание всех групп сохранено в schedule.json")

def clean_text(text):
    text = text.replace("\n", ", ")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

if __name__ == "__main__":
    parse_schedules()