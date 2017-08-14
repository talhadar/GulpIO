#!/usr/bin/env python
import random
import os
import json
import csv
import gzip
import glob
from abc import ABC, abstractmethod


from .utils import (get_single_video_path,
                    find_images_in_folder,
                    resize_images,
                    resize_by_short_edge,
                    burst_video_into_frames,
                    temp_dir_for_bursting,
                    )


class AbstractDatasetAdapter(ABC):  # pragma: no cover
    """ Base class adapter for gulping (video) datasets.

    Inherit from this class and implement the `iter_data` method. This method
    should iterate over your entire dataset and for each element return a
    dictionary with the following fields:

        id     : a unique(?) ID for the element.
        frames : a list of frames (PIL images, numpy arrays..)
        meta   : a dictionary with arbitrary metadata (labels, start_time...)

    For examples, see the custom adapters below.

    """

    @abstractmethod
    def iter_data(self, slice_element=None):
        return NotImplementedError

    @abstractmethod
    def __len__(self):
        return NotImplementedError


class Custom20BNJsonAdapter(object):

    def __init__(self, json_file, folder, output_folder,
                 shuffle=False, frame_size=-1, frame_rate=8,
                 shm_dir_path='/dev/shm'):
        self.json_file = json_file
        if json_file.endswith('.json.gz'):
            self.data = self.read_gz_json(json_file)
        elif json_file.endswith('.json'):
            self.data = self.read_json(json_file)
        else:
            raise RuntimeError('Wrong data file format (.json.gz or .json)')
        self.output_folder = output_folder
        self.label2idx = self.create_label2idx_dict()
        self.folder = folder
        self.shuffle = shuffle
        self.frame_size = frame_size
        self.frame_rate = frame_rate
        self.shm_dir_path = shm_dir_path
        self.all_meta = self.get_meta()
        if self.shuffle:
            random.shuffle(self.all_meta)

    def read_json(self, json_file):
        with open(json_file, 'r') as f:
            content = json.load(f)
        return content

    def read_gz_json(self, gz_json_file):
        with gzip.open(gz_json_file, 'rt') as fp:
            content = json.load(fp)
        return content

    def get_meta(self):
        return [{'id': entry['id'],
                 'label': entry['template'],
                 'idx': self.label2idx[entry['template']]}
                for entry in self.data]

    def create_label2idx_dict(self):
        labels = sorted(set([item['template'] for item in self.data]))
        label2idx = {}
        label_counter = 0
        for label_counter, label in enumerate(labels):
            label2idx[label] = label_counter
        return label2idx

    def write_label2idx_dict(self):
        json.dump(self.label2idx,
                  open(os.path.join(self.output_folder, 'label2idx.json'),
                       'w'))

    def __len__(self):
        return len(self.data)

    def iter_data(self, slice_element=None):
        slice_element = slice_element or slice(0, len(self))
        for meta in self.all_meta[slice_element]:
            video_folder = os.path.join(self.folder, str(meta['id']))
            video_path = get_single_video_path(video_folder, format_='mp4')
            with temp_dir_for_bursting(self.shm_dir_path) as temp_burst_dir:
                frame_paths = burst_video_into_frames(
                    video_path, temp_burst_dir, frame_rate=self.frame_rate)
                frames = list(resize_images(frame_paths, self.frame_size))
            result = {'meta': meta,
                      'frames': frames,
                      'id': meta['id']}
            yield result
        else:
            self.write_label2idx_dict()


class OpenSource20BNAdapter(object):

    def __init__(self, csv_file, folder, output_folder,
                 shuffle=False, frame_size=-1, shm_dir_path='/dev/shm'):
        self.data = self.read_csv(csv_file)
        self.output_folder = output_folder
        self.label2idx = self.create_label2idx_dict()
        self.folder = folder
        self.shuffle = shuffle
        self.frame_size = frame_size
        self.shm_dir_path = shm_dir_path
        self.all_meta = self.get_meta()
        if self.shuffle:
            random.shuffle(self.all_meta)

    def read_csv(self, csv_file):
        with open(csv_file, newline='\n') as f:
            content = csv.reader(f, delimiter=';')
            data = []
            for row in content:
                data.append({'id': row[0], 'label': row[1]})
        return data

    def get_meta(self):
        return [{'id': entry['id'],
                 'label': entry['label'],
                 'idx': self.label2idx[entry['label']]}
                for entry in self.data]

    def create_label2idx_dict(self):
        labels = sorted(set([item['label'] for item in self.data]))
        label2idx = {}
        label_counter = 0
        for label_counter, label in enumerate(labels):
            label2idx[label] = label_counter
        return label2idx

    def __len__(self):
        return len(self.data)

    def write_label2idx_dict(self):
        json.dump(self.label2idx,
                  open(os.path.join(self.output_folder, 'label2idx.json'),
                       'w'))

    def iter_data(self, slice_element=None):
        slice_element = slice_element or slice(0, len(self))
        for meta in self.all_meta[slice_element]:
            video_folder = os.path.join(self.folder, str(meta['id']))
            frame_paths = find_images_in_folder(video_folder, formats=['jpg'])
            frames = list(resize_images(frame_paths, self.frame_size))
            result = {'meta': meta,
                      'frames': frames,
                      'id': meta['id']}
            yield result
        else:
            self.write_label2idx_dict()


class ImageListAdapter():
    r"""Give a list.txt in format:

        img_path,label_name
        ...

        and it iterates through images/
    """

    def __init__(self, input_file, output_folder, root_folder='',
                 shuffle=False, img_size=-1):
        self.item_list = [item.strip().split(',') for item in open(input_file, 'r')]
        self.output_folder = output_folder
        self.root_folder = root_folder
        print("root  -- ", self.root_folder)
        self.folder = root_folder
        self.data = self.parse_paths(self.item_list)
        self.label2idx = self.create_label2idx_dict()
        self.shuffle = shuffle
        self.img_size = img_size
        self.all_meta = self.get_meta()
        if self.shuffle:
            random.shuffle(self.all_meta)

    def parse_paths(self, item_list):
        data = []
        for img_path, label_name in item_list:
            img_name = os.path.basename(img_path)
            data.append({'id': img_name, 'label': label_name, 'path': img_path})
        return data

    def get_meta(self):
        return [{'id': entry['id'],
                 'label': entry['label'],
                 'path': entry['path'],
                 'idx': self.label2idx[entry['label']]}
                for entry in self.data]

    def create_label2idx_dict(self):
        labels = sorted(set([item['label'] for item in self.data]))
        label2idx = {}
        label_counter = 0
        for label_counter, label in enumerate(labels):
            label2idx[label] = label_counter
        return label2idx

    def __len__(self):
        return len(self.data)

    def write_label2idx_dict(self):
        json.dump(self.label2idx,
                  open(os.path.join(self.output_folder, 'label2idx.json'),
                       'w'))

    def iter_data(self, slice_element=None):
        slice_element = slice_element or slice(0, len(self))
        for meta in self.all_meta[slice_element]:
            img_path = os.path.join(self.root_folder, str(meta['path']))
            img = resize_by_short_edge(img_path, self.img_size)
            result = {'meta': meta,
                      'frames': [img],
                      'id': meta['id']}
            yield result
        else:
            self.write_label2idx_dict()


class ImageFolderAdapter():
    r"""Parse the given folder assuming each subfolder is a category and it
    includes the category images.
    """

    def __init__(self, folder, output_folder,
                 file_extensions=['.jpg'], shuffle=False,
                 img_size=-1):
        self.file_extensions = file_extensions
        self.data = self.parse_folder(folder)
        self.output_folder = output_folder
        self.label2idx = self.create_label2idx_dict()
        self.folder = folder
        self.shuffle = shuffle
        self.img_size = img_size
        self.all_meta = self.get_meta()
        if self.shuffle:
            random.shuffle(self.all_meta)

    def parse_folder(self, folder):
        img_paths = []
        for extension in self.file_extensions:
            search_pattern = os.path.join(folder+"**/*{}".format(extension))
            paths = glob.glob(search_pattern, recursive=True)
        img_paths.extend(paths)
        img_paths = sorted(img_paths)
        data = []
        for img_path in img_paths:
            path = os.path.dirname(img_path)
            category_name = path.split('/')[-1]
            img_name = os.path.basename(img_path)
            category_name = category_name
            data.append({'id': img_name, 'label': category_name, 'path': path})
        return data

    def get_meta(self):
        return [{'id': entry['id'],
                 'label': entry['label'],
                 'path': entry['path'],
                 'idx': self.label2idx[entry['label']]}
                for entry in self.data]

    def create_label2idx_dict(self):
        labels = sorted(set([item['label'] for item in self.data]))
        label2idx = {}
        label_counter = 0
        for label_counter, label in enumerate(labels):
            label2idx[label] = label_counter
        return label2idx

    def __len__(self):
        return len(self.data)

    def write_label2idx_dict(self):
        json.dump(self.label2idx,
                  open(os.path.join(self.output_folder, 'label2idx.json'),
                       'w'))

    def iter_data(self, slice_element=None):
        slice_element = slice_element or slice(0, len(self))
        for meta in self.all_meta[slice_element]:
            img_path = os.path.join(self.folder, str(meta['path']),
                                    str(meta['id']))
            img = resize_by_short_edge(img_path, self.img_size)
            result = {'meta': meta,
                      'frames': [img],
                      'id': meta['id']}
            yield result
        else:
            self.write_label2idx_dict()


# class Input_from_csv(object):
#
#     def __init__(self, csv_file, num_labels=None):
#         self.num_labels = num_labels
#         self.data = self.read_input_from_csv(csv_file)
#         self.label2idx = self.create_labels_dict()
#
#     def read_input_from_csv(self, csv_file):
#         print(" > Reading data list (csv)")
#         return pd.read_csv(csv_file)
#
#     def create_labels_dict(self):
#         labels = sorted(pd.unique(self.data['label']))
#         if self.num_labels:
#             assert len(labels) == self.num_labels
#         label2idx = {}
#         for i, label in enumerate(labels):
#             label2idx[label] = i
#         return label2idx
#
#     def get_data(self):
#         output = []
#         for idx, row in self.data.iterrows():
#             entry_dict = {}
#             entry_dict['id'] = row.youtube_id
#             entry_dict['label'] = row.label
#             entry_dict['start_time'] = row.time_start
#             entry_dict['end_time'] = row.time_end
#             output.append(entry_dict)
#         return output, self.label2idx
